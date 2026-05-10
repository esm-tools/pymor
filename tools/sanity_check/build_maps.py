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
    """Pick one record per variable.

    Prefer files that look like full 2D fields (CMIP branding `hxy-*` or
    `hxyg-*`) over horizontal-mean / zonal / basin scalars (`hm-*`, `hyb-*`,
    `hxx-*`). Then prefer monthly > daily > sub-daily, then alphabetical.
    """

    def _spatial_rank(fname: str) -> int:
        n = fname.lower()
        # Prefer full xy fields
        if "-hxy-" in n or "-hxyg-" in n:
            return 0
        if "-hxz-" in n:
            return 1
        # Demote 1D / scalar / basin / global-mean brandings
        if "-hm-" in n or "-hyb-" in n or "-hxx-" in n or "-hyy-" in n:
            return 9
        return 5

    def _key(rec: Dict[str, Any]) -> Tuple[int, int, str]:
        fname = Path(str(rec.get("file", ""))).name
        return (_spatial_rank(fname), _freq_rank(fname), fname)

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


def _reduce_to_panels(da, parent=None):
    """Reduce to time-min / time-mean / time-max 2D fields.

    Returns (panels, notes) where panels is a dict
    {"min": DataArray, "mean": DataArray, "max": DataArray}, each with at most
    2 dims (the spatial ones). Returns ({"mean": DataArray}, notes) if no time
    dim is present.
    """

    notes: List[str] = []
    panels: Dict[str, Any] = {}

    # Discover spatial dims via the coordinates that carry lat/lon. This is the
    # robust signal — the dim could be named anything (cell, nod2, ncells, ...).
    # We ONLY trust the coords; substring fallback was unsafe because some pycmor
    # files mis-name the model-level dim "longitude" (size 137 in IFS L137).
    spatial_dims = set()
    for coord_name in ("lat", "latitude", "lon", "longitude"):
        if coord_name in da.coords:
            spatial_dims.update(da.coords[coord_name].dims)
    if parent is not None:
        for coord_name in ("lat", "latitude", "lon", "longitude"):
            if coord_name in parent.coords:
                spatial_dims.update(parent.coords[coord_name].dims)

    # Fallback substring hints, used ONLY when lat/lon coords don't reveal a
    # spatial dim at all. Restricted to unambiguous unstructured-grid hints so
    # we never accidentally classify a level-style dim as spatial.
    fallback_hints = (
        "ncells", "nod2", "node", "ncell", "ncol",
    )

    def is_spatial(dim_name: str) -> bool:
        if dim_name in spatial_dims:
            return True
        if spatial_dims:
            # We already have a definitive answer from the coords; don't
            # second-guess it with substring matches.
            return False
        return any(h in dim_name.lower() for h in fallback_hints)

    # 1) collapse non-time, non-spatial dims first (level/tile/basin) by isel(0)
    time_dims = [d for d in da.dims if d.lower() in ("time", "t")]
    while True:
        non_spatial = [d for d in da.dims
                       if not is_spatial(d) and d not in time_dims]
        if not non_spatial:
            break
        d0 = non_spatial[0]
        # Try isel(0); if the slice is all-NaN (e.g. surface level of
        # ocean vertical diffusivity, which is defined only at interior
        # interfaces) walk through the dim until we find a slice with at
        # least some finite values. Cap the search at ~12 attempts.
        try:
            n = int(da.sizes[d0])
            chosen = 0
            tried_levels = list(range(min(n, 12)))
            for idx in tried_levels:
                slab = da.isel({d0: idx})
                vals = slab.values
                if np.isfinite(vals).any():
                    chosen = idx
                    break
            else:
                # No finite slice in the first 12 — fall back to 0
                chosen = 0
            da = da.isel({d0: chosen})
            notes.append(f"{d0}={chosen}")
        except Exception:
            break
        if len(non_spatial) == 1:
            break

    # 2) Compute time-min/mean/max along the time dim. If multiple time dims,
    # collapse them all (rare).
    if time_dims:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            panels["min"] = da.min(dim=time_dims, keep_attrs=True)
            panels["mean"] = da.mean(dim=time_dims, keep_attrs=True)
            panels["max"] = da.max(dim=time_dims, keep_attrs=True)
        notes.append(f"min/mean/max({','.join(time_dims)})")
        # representative for ndim safety check below
        da = panels["mean"]
    else:
        panels["mean"] = da

    # 3) if still > 2 dims (e.g. weird coord situation), reduce the leading
    # dims by index 0 until ndim <= 2.
    while da.ndim > 2:
        d0 = da.dims[0]
        try:
            for k in list(panels):
                panels[k] = panels[k].isel({d0: 0})
            da = panels.get("mean", da)
            notes.append(f"{d0}=0")
        except Exception:
            break

    return panels, notes


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

    # Case B: data 1D (unstructured) — return raw point cloud for scatter.
    # 1deg binning bleeds coastal values inland, so prefer native scatter
    # which honours the mesh footprint exactly.
    if da.ndim == 1:
        if lat is None or lon is None:
            raise ValueError("1D data but no lat/lon coords")
        if lat.size != da.size or lon.size != da.size:
            raise ValueError(
                f"1D data of size {da.size} but lat/lon have sizes "
                f"{lat.size}/{lon.size}"
            )
        return (
            np.asarray(lon.values, dtype=float),
            np.asarray(lat.values, dtype=float),
            np.asarray(da.values, dtype=float),
            "scatter",
        )

    raise ValueError(f"unsupported reduced ndim={da.ndim}")


def _has_spatial(da, parent=None) -> bool:
    """True if the DataArray's lat/lon coords reveal a spatial dim it shares."""
    spatial_dims = set()
    for src in (da, parent):
        if src is None:
            continue
        for cn in ("lat", "latitude", "lon", "longitude"):
            if cn in getattr(src, "coords", {}):
                spatial_dims.update(src.coords[cn].dims)
    if not spatial_dims:
        # FESOM nod2 or similar where the file uses a known unstructured-grid
        # name without a coord. Fall back to substring detection on da.dims.
        for dn in da.dims:
            n = dn.lower()
            if any(h in n for h in ("ncells", "nod2", "node", "ncell", "ncol",
                                     "cell")):
                return True
        return False
    return any(d in da.dims for d in spatial_dims)


def _render_timeseries(out_path: Path, var: str, units: str, da, ds) -> None:
    """Plot a 1D time series for variables with only a time dim.

    Used for hemispheric/global scalars (siarea, siextent, sivol, masso, ...)
    where a map is meaningless.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Reduce any non-time dim by isel(0) until only the time-like dim remains.
    while da.ndim > 1:
        non_time = [d for d in da.dims if d.lower() not in ("time", "t")]
        if not non_time:
            break
        d0 = non_time[0]
        try:
            da = da.isel({d0: 0})
        except Exception:
            break

    values = np.asarray(da.values, dtype=float).ravel()
    if values.size == 0 or not np.isfinite(values).any():
        _placeholder_png(out_path, f"{var}: empty or all-NaN time series")
        return

    # x axis: prefer the time coord if present, else integer index. Don't try
    # to decode cftime — just show numeric values from the file's time coord.
    x = None
    tcoord_name = None
    for cn in ("time", "time_centered", "t"):
        if cn in da.coords:
            tcoord_name = cn
            x = np.asarray(da.coords[cn].values, dtype=float).ravel()
            break
    if x is None or x.size != values.size:
        x = np.arange(values.size, dtype=float)
        tcoord_name = "step"

    fig = plt.figure(figsize=(6.0, 2.4), dpi=100)
    ax = fig.add_subplot(111)
    ax.plot(x, values, color="#1a6", linewidth=1.4)
    ax.scatter(x, values, color="#1a6", s=10)
    ax.set_xlabel(tcoord_name, fontsize=8)
    ax.set_ylabel(units or "", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, linewidth=0.4, alpha=0.4)
    vmin, vmax = float(np.nanmin(values)), float(np.nanmax(values))
    vmean = float(np.nanmean(values))
    title = (f"{var}  (time series, {units or '?'})\n"
             f"min={vmin:.3g}  mean={vmean:.3g}  max={vmax:.3g}")
    ax.set_title(title, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=100, bbox_inches="tight")
    plt.close(fig)


def _norm_for(vmin, vmax):
    """Pick a (cmap, norm) pair that fills the colorbar with the actual data range."""
    if not (np.isfinite(vmin) and np.isfinite(vmax)) or vmin == vmax:
        return "viridis", plt.Normalize(vmin=vmin or 0.0, vmax=vmax or 1.0)
    if vmin >= 0.0 or vmax <= 0.0:
        return "viridis", plt.Normalize(vmin=vmin, vmax=vmax)
    ratio = abs(vmin) / max(abs(vmax), 1e-30)
    if 0.2 <= ratio <= 5.0:
        absmax = max(abs(vmin), abs(vmax))
        return "RdBu_r", plt.Normalize(vmin=-absmax, vmax=absmax)
    try:
        from matplotlib.colors import TwoSlopeNorm
        return "RdBu_r", TwoSlopeNorm(vcenter=0.0, vmin=vmin, vmax=vmax)
    except Exception:
        return "RdBu_r", plt.Normalize(vmin=vmin, vmax=vmax)


def _render_map(out_path: Path, var: str, units: str, notes: Sequence[str],
                panel_data: Dict[str, Tuple[Any, Any, Any, str]]) -> None:
    """Render a horizontal 3-panel figure: time-min / time-mean / time-max.

    panel_data maps "min"/"mean"/"max" to (lon, lat, values_2d, mode) tuples.
    If only the "mean" key is present (no time dim) draws a single panel.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    keys = [k for k in ("min", "mean", "max") if k in panel_data]
    if not keys:
        _placeholder_png(out_path, f"{var}: no panels to draw")
        return

    # If every panel is all-NaN, write the standard placeholder
    if all(not np.isfinite(panel_data[k][2]).any() for k in keys):
        _placeholder_png(out_path, f"{var}: all-NaN field")
        return

    n = len(keys)
    fig_w = 4.5 * n if n > 1 else 5.0
    fig = plt.figure(figsize=(fig_w, 2.6), dpi=100)
    for i, k in enumerate(keys):
        lon, lat, values_2d, mode = panel_data[k]
        if not np.isfinite(values_2d).any():
            ax = fig.add_subplot(1, n, i + 1)
            ax.set_facecolor("#f4f4f4")
            ax.text(0.5, 0.5, f"all-NaN", ha="center", va="center",
                    transform=ax.transAxes, fontsize=8, color="#888")
            ax.set_title(f"time-{k}", fontsize=8)
            ax.set_xticks([]); ax.set_yticks([])
            continue
        vmin = float(np.nanmin(values_2d))
        vmax = float(np.nanmax(values_2d))
        cmap, norm = _norm_for(vmin, vmax)
        ax = fig.add_subplot(1, n, i + 1)
        ax.set_facecolor("#f4f4f4")
        if mode == "scatter":
            # FESOM-style point cloud: native node lat/lon, no binning.
            # Drop non-finite points before plotting so masked nodes
            # leave their pixel transparent.
            finite = np.isfinite(values_2d)
            xv = np.asarray(lon)[finite]
            yv = np.asarray(lat)[finite]
            cv = np.asarray(values_2d)[finite]
            # Wrap longitudes to -180..180 so both 0..360 and -180..180
            # source conventions plot on the same axis range.
            xv = np.where(xv > 180.0, xv - 360.0, xv)
            xv = np.where(xv < -180.0, xv + 360.0, xv)
            # Marker size scales with how many nodes there are; for HR
            # FESOM (~6e6 nodes) s=0.5 just covers the mesh footprint.
            s = max(0.2, min(2.0, 6.0e6 / max(cv.size, 1)))
            mesh = ax.scatter(xv, yv, c=cv, cmap=cmap, norm=norm,
                              s=s, marker=",", linewidths=0,
                              rasterized=True)
            ax.set_xlim(-180, 180)
            ax.set_ylim(-90, 90)
        else:
            mesh = ax.pcolormesh(lon, lat, values_2d, cmap=cmap, norm=norm,
                                 shading="auto")
        ax.set_xlabel("lon", fontsize=7)
        if i == 0:
            ax.set_ylabel("lat", fontsize=7)
        ax.tick_params(labelsize=6)
        ax.set_title(f"time-{k}\nmin={vmin:.3g} max={vmax:.3g}", fontsize=7)
        cb = fig.colorbar(mesh, ax=ax, fraction=0.04, pad=0.02)
        cb.ax.tick_params(labelsize=6)
        if units and i == n - 1:
            cb.set_label(units, fontsize=7)

    sup = f"{var}  ({units or '?'})"
    if notes:
        sup += f"  [{', '.join(notes)}]"
    fig.suptitle(sup, fontsize=8, y=1.02)
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
        # Hemispheric/global scalars (siarea, siextent, sivol, masso, ...)
        # have no spatial dim; plot a time series instead of a map.
        if not _has_spatial(da, parent=ds):
            _render_timeseries(out_path, var, units, da, ds)
            ds.close()
            return var, "ok-timeseries", fname
        panels, notes = _reduce_to_panels(da, parent=ds)
        # Build pcolormesh inputs for each panel separately. The grid (lon,
        # lat, mode) is the same across all three; just the values differ.
        panel_data: Dict[str, Tuple[Any, Any, Any, str]] = {}
        for k, panel_da in panels.items():
            lon, lat, values_2d, mode = _make_pcolormesh_inputs(panel_da, ds)
            panel_data[k] = (lon, lat, values_2d, mode)
        _render_map(out_path, var, units, notes, panel_data)
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
