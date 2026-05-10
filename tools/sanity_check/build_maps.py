#!/usr/bin/env python3
"""Build small geographic map PNGs per CMOR variable from the sanity-check JSONL.

For each variable in the sanity-check JSONL, pick a representative monthly file
(else daily, else 1/3-hourly), open it with xarray, reduce to a 2D (lat, lon)
field via time-mean and index-0 selection on any other non-spatial dim, and
render a small ~500x240 px PNG using only matplotlib (no cartopy).

Usage::

    python build_maps.py --jsonl PATH --out-dir PATH [--parallel N]

Defaults:

* ``--jsonl``    /tmp/sanity_check_results.jsonl
* ``--out-dir``  tools/sanity_check/reports/<label>_html (label derived from
                 ``/<label>/cmorized/`` in any file path)
* ``--parallel`` 8

The script is self-contained (no project imports) and uses a non-interactive
matplotlib backend so it can run on headless workers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import warnings
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Non-interactive backend MUST be set before importing pyplot.
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)


# ---------------------------------------------------------------------------
# Frequency ranking helpers
# ---------------------------------------------------------------------------

# Lower number == preferred.
_FREQ_TOKENS: List[Tuple[str, int]] = [
    ("_yr_", 0),
    ("_mon_", 1),
    ("_day_", 2),
    ("_6hr_", 3),
    ("_3hr_", 4),
    ("_1hr_", 5),
    ("_subhr_", 6),
]


def _freq_rank(filename: str) -> int:
    """Return a sortable rank from the frequency infix in a filename."""

    name = filename.lower()
    for token, rank in _FREQ_TOKENS:
        if token in name:
            return rank
    return 99


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------


def _parse_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(
                    json.loads(line, parse_constant=lambda x: float("nan"))
                )
            except json.JSONDecodeError:
                continue
    return records


def _infer_label(records: Sequence[Dict[str, Any]]) -> str:
    """Mirror build_html_report.infer_label."""

    for rec in records:
        path = rec.get("file")
        if not path:
            continue
        m = re.search(r"/([^/]+)/cmorized/", path)
        if m:
            return m.group(1)
    return "sanity-check"


def _pick_representative(recs: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pick one record per variable: prefer monthly, then daily, then 1hr."""

    def _key(rec: Dict[str, Any]) -> Tuple[int, str]:
        fname = Path(str(rec.get("file", ""))).name
        return (_freq_rank(fname), fname)

    valid = [r for r in recs if r.get("file")]
    if not valid:
        return None
    return sorted(valid, key=_key)[0]


# ---------------------------------------------------------------------------
# Plot helpers
# ---------------------------------------------------------------------------


_BOUND_NAME_HINTS = (
    "bnds",
    "bounds",
    "vertices",
    "_bnd",
    "time_bnds",
)

_NON_SPATIAL_DIM_HINTS = (
    "lev",
    "plev",
    "alev",
    "depth",
    "olevel",
    "olevhalf",
    "landuse",
    "vegtype",
    "basin",
    "simp",
    "spectband",
    "tau",
    "type",
    "site",
    "scatratio",
    "soil_carbon_pool",
    "vegtype",
)


def _is_bound_name(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in _BOUND_NAME_HINTS)


def _placeholder_png(out_path: Path, message: str) -> None:
    """Write a 480x120 placeholder PNG with centered message text."""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(4.8, 1.2), dpi=100)
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(
        0.5,
        0.5,
        message,
        ha="center",
        va="center",
        wrap=True,
        fontsize=9,
        family="monospace",
    )
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)


def _pick_primary_var(ds, var: str) -> Optional[str]:
    """Pick the data variable to plot."""

    data_vars = list(ds.data_vars)
    if not data_vars:
        return None
    if var in data_vars:
        return var
    # else most-dimensional non-bounds variable
    candidates = [n for n in data_vars if not _is_bound_name(n)]
    if not candidates:
        candidates = data_vars
    candidates.sort(key=lambda n: -ds[n].ndim)
    return candidates[0]


def _find_latlon_coords(ds, da):
    """Return (lat_coord, lon_coord) DataArrays or (None, None)."""

    candidates_lat = ("lat", "latitude", "nav_lat", "y")
    candidates_lon = ("lon", "longitude", "nav_lon", "x")

    lat = None
    lon = None
    for name in candidates_lat:
        if name in ds.coords:
            lat = ds[name]
            break
        if name in ds.variables:
            lat = ds[name]
            break
    for name in candidates_lon:
        if name in ds.coords:
            lon = ds[name]
            break
        if name in ds.variables:
            lon = ds[name]
            break
    return lat, lon


def _reduce_to_2d(da):
    """Reduce a DataArray to a (lat, lon) or 1D (ncells,) field.

    Strategy: time-mean across any time-like dim, then index-0 for any other
    non-spatial dim until we land on at most 2 dims (the spatial ones).
    Returns (reduced DataArray, list of notes).
    """

    notes: List[str] = []

    spatial_hints = ("lat", "latitude", "lon", "longitude", "ncells", "nod2", "elem")

    # 1) time-mean
    time_dims = [d for d in da.dims if d.lower() in ("time", "t")]
    for tdim in time_dims:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            da = da.mean(dim=tdim, keep_attrs=True)
        notes.append(f"mean({tdim})")

    # 2) collapse all non-spatial dims by isel(0)
    while True:
        non_spatial = [
            d
            for d in da.dims
            if not any(h in d.lower() for h in spatial_hints)
        ]
        if not non_spatial:
            break
        # safety: if more than 2 dims and none look spatial, just keep first two.
        d0 = non_spatial[0]
        try:
            da = da.isel({d0: 0})
            notes.append(f"{d0}=0")
        except Exception:
            break
        if da.ndim <= 2:
            # might still have a leftover non-spatial dim; loop continues.
            pass
        if len(non_spatial) == 1:
            break

    # 3) if still > 2 dims (e.g. weird coord situation), reduce the leading
    # dims by index 0 until ndim <= 2.
    while da.ndim > 2:
        d0 = da.dims[0]
        try:
            da = da.isel({d0: 0})
            notes.append(f"{d0}=0")
        except Exception:
            break

    return da, notes


def _bin_unstructured(values, lat1d, lon1d):
    """Bin point-cloud (lat, lon, value) onto a 1deg lat/lon mesh.

    Returns (lon_edges, lat_edges, gridded_2d) ready for pcolormesh.
    """

    values = np.asarray(values, dtype=float).ravel()
    lat1d = np.asarray(lat1d, dtype=float).ravel()
    lon1d = np.asarray(lon1d, dtype=float).ravel()

    # detect lon convention
    lon_min = float(np.nanmin(lon1d))
    if lon_min < -1.0:
        lon_edges = np.arange(-180.0, 180.001, 1.0)
    else:
        lon_edges = np.arange(0.0, 360.001, 1.0)
    lat_edges = np.arange(-90.0, 90.001, 1.0)

    # mask non-finite
    finite = np.isfinite(values) & np.isfinite(lat1d) & np.isfinite(lon1d)
    values = values[finite]
    lat1d = lat1d[finite]
    lon1d = lon1d[finite]

    # wrap lon to chosen edges
    if lon_edges[0] >= 0.0:
        lon1d = np.where(lon1d < 0.0, lon1d + 360.0, lon1d)
    else:
        lon1d = np.where(lon1d > 180.0, lon1d - 360.0, lon1d)

    if values.size == 0:
        ny = lat_edges.size - 1
        nx = lon_edges.size - 1
        return lon_edges, lat_edges, np.full((ny, nx), np.nan)

    sums, _, _ = np.histogram2d(
        lat1d, lon1d, bins=[lat_edges, lon_edges], weights=values
    )
    counts, _, _ = np.histogram2d(
        lat1d, lon1d, bins=[lat_edges, lon_edges]
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        gridded = np.where(counts > 0, sums / counts, np.nan)
    return lon_edges, lat_edges, gridded


def _coords_2d_to_grid(values_2d, lat2d, lon2d):
    """Treat 2D-coord rectilinear-ish data as a flatten + bin point cloud."""

    return _bin_unstructured(values_2d, lat2d, lon2d)


def _make_pcolormesh_inputs(da, ds):
    """Return (lon_edges_or_centers, lat_edges_or_centers, values_2d, mode).

    mode is "regular" if lat/lon are 1D and values_2d is already aligned; else
    "binned" meaning the lon/lat are edges of a 1deg grid.
    """

    lat, lon = _find_latlon_coords(ds, da)

    # Case A: data already 2D
    if da.ndim == 2:
        if lat is not None and lon is not None and lat.ndim == 1 and lon.ndim == 1:
            # rectilinear; verify dims match
            if set(da.dims) >= {lat.dims[0], lon.dims[0]}:
                # ensure shape (lat, lon)
                want = (lat.dims[0], lon.dims[0])
                if da.dims != want:
                    da = da.transpose(*want)
                lon_arr = np.asarray(lon.values, dtype=float)
                lat_arr = np.asarray(lat.values, dtype=float)
                values_2d = np.asarray(da.values, dtype=float)
                return lon_arr, lat_arr, values_2d, "regular"
        if lat is not None and lon is not None and lat.ndim == 2 and lon.ndim == 2:
            lon_e, lat_e, gridded = _coords_2d_to_grid(
                np.asarray(da.values, dtype=float),
                np.asarray(lat.values, dtype=float),
                np.asarray(lon.values, dtype=float),
            )
            return lon_e, lat_e, gridded, "binned"
        # 2D but no lat/lon? bail out
        raise ValueError("2D data but lat/lon coords are missing or unusable")

    # Case B: data 1D (unstructured)
    if da.ndim == 1:
        if lat is None or lon is None:
            raise ValueError("1D data but no lat/lon coords")
        if lat.size != da.size or lon.size != da.size:
            raise ValueError(
                f"1D data of size {da.size} but lat/lon have sizes "
                f"{lat.size}/{lon.size}"
            )
        lon_e, lat_e, gridded = _bin_unstructured(
            np.asarray(da.values, dtype=float),
            np.asarray(lat.values, dtype=float),
            np.asarray(lon.values, dtype=float),
        )
        return lon_e, lat_e, gridded, "binned"

    raise ValueError(f"unsupported reduced ndim={da.ndim}")


def _render_map(out_path: Path, var: str, units: str, notes: Sequence[str],
                lon, lat, values_2d, mode: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    finite = np.isfinite(values_2d)
    if not finite.any():
        _placeholder_png(out_path, f"{var}: all-NaN field")
        return

    vmin = float(np.nanmin(values_2d))
    vmax = float(np.nanmax(values_2d))
    if vmin < 0.0 < vmax:
        cmap = "RdBu_r"
        absmax = max(abs(vmin), abs(vmax))
        norm = plt.Normalize(vmin=-absmax, vmax=absmax)
    else:
        cmap = "viridis"
        norm = plt.Normalize(vmin=vmin, vmax=vmax)

    fig = plt.figure(figsize=(5.0, 2.4), dpi=100)
    ax = fig.add_subplot(111)
    ax.set_facecolor("#f4f4f4")

    mesh = ax.pcolormesh(lon, lat, values_2d, cmap=cmap, norm=norm, shading="auto")

    ax.set_xlabel("lon", fontsize=8)
    ax.set_ylabel("lat", fontsize=8)
    ax.tick_params(labelsize=7)
    title = f"{var}  (time-mean, {units or '?'})"
    if notes:
        title += f"\n[{', '.join(notes)}]"
    ax.set_title(title, fontsize=8)

    cb = fig.colorbar(mesh, ax=ax, fraction=0.04, pad=0.02)
    cb.ax.tick_params(labelsize=7)
    if units:
        cb.set_label(units, fontsize=7)

    fig.tight_layout()
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _process_one(args_tuple: Tuple[str, str, Dict[str, Any], str]) -> Tuple[str, str, str]:
    """Render one variable. Returns (var, status, fname)."""

    var, file_path, rec, out_dir = args_tuple
    out_path = Path(out_dir) / "assets" / "maps" / f"{var}.png"
    fname = Path(file_path).name

    # Resume: skip if PNG already exists (and is non-empty).
    if out_path.exists() and out_path.stat().st_size > 0:
        return var, "skip-exists", fname

    try:
        import xarray as xr  # noqa: WPS433
    except Exception as exc:  # pragma: no cover
        _placeholder_png(out_path, f"xarray import failed: {exc}")
        return var, "no-xarray", fname

    try:
        ds = xr.open_dataset(file_path, decode_times=False)
    except Exception as exc:
        _placeholder_png(out_path, f"open failed: {exc}")
        return var, "open-failed", fname

    try:
        primary = _pick_primary_var(ds, var)
        if primary is None:
            _placeholder_png(out_path, f"{var}: no data variables")
            ds.close()
            return var, "no-data-vars", fname
        da = ds[primary]
        units = str(rec.get("units_in_file") or da.attrs.get("units") or "")
        reduced, notes = _reduce_to_2d(da)
        lon, lat, values_2d, mode = _make_pcolormesh_inputs(reduced, ds)
        _render_map(out_path, var, units, notes, lon, lat, values_2d, mode)
        ds.close()
        return var, "ok", fname
    except Exception as exc:
        try:
            ds.close()
        except Exception:
            pass
        _placeholder_png(out_path, f"{var}: {exc}")
        return var, "err", fname


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_jobs(records: Sequence[Dict[str, Any]], out_dir: Path) -> List[Tuple[str, str, Dict[str, Any], str]]:
    by_var: Dict[str, List[Dict[str, Any]]] = {}
    for rec in records:
        var = rec.get("var")
        if not var:
            continue
        by_var.setdefault(str(var), []).append(rec)

    jobs: List[Tuple[str, str, Dict[str, Any], str]] = []
    for var, recs in sorted(by_var.items()):
        rep = _pick_representative(recs)
        if not rep:
            continue
        file_path = str(rep.get("file") or "")
        if not file_path:
            continue
        jobs.append((var, file_path, rep, str(out_dir)))
    return jobs


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--jsonl",
        default="/tmp/sanity_check_results.jsonl",
        help="Sanity-check JSONL output (default: %(default)s)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output dir (default: tools/sanity_check/reports/<label>_html)",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=8,
        help="Number of worker processes (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"error: jsonl not found: {jsonl_path}", file=sys.stderr)
        return 2

    records = _parse_jsonl(jsonl_path)
    if not records:
        print("error: no records in jsonl", file=sys.stderr)
        return 2

    label = _infer_label(records)
    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = (
            Path(__file__).resolve().parent / "reports" / f"{label}_html"
        )
    (out_dir / "assets" / "maps").mkdir(parents=True, exist_ok=True)

    jobs = _build_jobs(records, out_dir)
    if not jobs:
        print("error: no variables to render", file=sys.stderr)
        return 2

    nproc = max(1, int(args.parallel))
    if nproc == 1:
        for job in jobs:
            var, status, fname = _process_one(job)
            print(f"{var}\t{status}\t{fname}")
    else:
        ctx = get_context("spawn")
        with ctx.Pool(processes=nproc) as pool:
            for var, status, fname in pool.imap_unordered(_process_one, jobs):
                print(f"{var}\t{status}\t{fname}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
