"""
This module contains functions for handling file-related operations in the pycmor package.
It includes functions for creating filepaths based on given rules and datasets, and for
saving the resulting datasets to the generated filepaths.



Table 2: Precision of time labels used in file names
|---------------+-------------------+-----------------------------------------------|
| Frequency     | Precision of time | Notes                                         |
|               | label             |                                               |
|---------------+-------------------+-----------------------------------------------|
| yr, dec,      | “yyyy”            | Label with the years recorded in the first    |
| yrPt          |                   | and last coordinate values.                   |
|---------------+-------------------+-----------------------------------------------|
| mon, monC     | “yyyyMM”          | For “mon”, label with the months recorded in  |
|               |                   | the first and last coordinate values; for     |
|               |                   | “monC” label with the first and last months   |
|               |                   | contributing to the climatology.              |
|---------------+-------------------+-----------------------------------------------|
| day           | “yyyyMMdd”        | Label with the days recorded in the first and |
|               |                   | last coordinate values.                       |
|---------------+-------------------+-----------------------------------------------|
| 6hr, 3hr,     | “yyyyMMddhhmm”    | Label 1hrCM files with the beginning of the   |
| 1hr,          |                   | first hour and the end of the last hour       |
| 1hrCM, 6hrPt, |                   | contributing to climatology (rounded to the   |
| 3hrPt,        |                   | nearest minute); for other frequencies in     |
| 1hrPt         |                   | this category, label with the first and last  |
|               |                   | time-coordinate values (rounded to the        |
|               |                   | nearest minute).                              |
|---------------+-------------------+-----------------------------------------------|
| subhrPt       | “yyyyMMddhhmmss”  | Label with the first and last time-coordinate |
|               |                   | values (rounded to the nearest second)        |
|---------------+-------------------+-----------------------------------------------|
| fx            | Omit time label   | This frequency applies to variables that are  |
|               |                   | independent of time (“fixed”).                |
|---------------+-------------------+-----------------------------------------------|

"""

import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from xarray.core.utils import is_scalar

from ..core.logging import logger
from .bounds import add_bounds_from_coords
from .chunking import (
    calculate_chunks_even_divisor,
    calculate_chunks_iterative,
    calculate_chunks_simple,
    get_encoding_with_chunks,
)
from .dataset_helpers import get_time_label, has_time_axis
from .global_attributes import _collect_external_cell_measures
from .time_bounds import (
    _force_canonical_time_encoding,
    canonicalize_time_in_encoding_dict,
)

import dask


class SaveTimeout(Exception):
    """Raised by :class:`_Heartbeat` when the watched path stops growing
    for longer than the configured timeout. Caught by ``save_dataset``'s
    retry loop (Option E of PLAN_save_dataset_reliability.md).

    Under our failure mode (worker blocked in a POSIX write syscall on
    Lustre), the originally-stuck worker may continue to leak its slot
    until SLURM kills the job — but the retry runs on a different worker
    and can succeed. See PLAN §E for the realistic semantics.
    """


class _Heartbeat:
    """Context manager that emits periodic ``logger.info`` "still running"
    lines while a long-running block executes. Used by ``save_dataset``
    so multi-minute operations don't appear as silent stalls in tier-job
    logs (the rule-level Prefect events fire only at task boundaries,
    so a 30-minute ``to_netcdf`` looks like a hang to monitoring).

    The interval defaults to 60 s and is overridable via the env var
    ``PYCMOR_HEARTBEAT_INTERVAL_S`` (set to 0 to disable). The thread
    is a daemon and exits cleanly when the with-block ends; if the
    block raises, the thread still terminates because of the
    ``threading.Event`` wait.

    Optional file-size watchdog (Option E of
    PLAN_save_dataset_reliability.md): if ``watch_path`` is given,
    poll its size; if it does not grow for ``timeout_minutes``
    (default ``PYCMOR_SAVE_TIMEOUT_MIN`` env, fallback 15 min),
    flag a timeout — ``__exit__`` raises :class:`SaveTimeout`.

    A timeout-detected via this watchdog *does not* unblock the worker
    that's stuck in a POSIX write syscall — Python-level ``cancel()``
    cannot interrupt a kernel-level blocking call. The retry runs on a
    different dask worker; the original may leak its slot until SLURM
    kills the job. See PLAN_save_dataset_reliability.md §E for the
    realistic semantics this design chooses.
    """

    def __init__(self, label, interval=None, watch_path=None, timeout_minutes=None):
        if interval is None:
            try:
                interval = float(os.environ.get("PYCMOR_HEARTBEAT_INTERVAL_S", "60"))
            except (TypeError, ValueError):
                interval = 60.0
        if timeout_minutes is None:
            try:
                timeout_minutes = float(os.environ.get("PYCMOR_SAVE_TIMEOUT_MIN", "15"))
            except (TypeError, ValueError):
                timeout_minutes = 15.0
        self.label = label
        self.interval = interval
        self.watch_path = watch_path
        self.timeout_s = float(timeout_minutes) * 60.0
        self._stop = threading.Event()
        self._t0 = None
        self._th = None
        self._timed_out = False
        self._last_size = -1
        self._last_progress_ts = None

    @property
    def timed_out(self):
        return self._timed_out

    def __enter__(self):
        if self.interval <= 0:
            return self
        self._t0 = time.monotonic()
        self._last_progress_ts = time.monotonic()

        def _tick():
            n = 0
            while not self._stop.wait(self.interval):
                n += 1
                elapsed = time.monotonic() - self._t0
                logger.info(
                    f"  ⟳ {self.label} still running "
                    f"(t={elapsed:.0f}s, heartbeat #{n})"
                )
                # Watchdog: poll watch_path size and detect stalls.
                # watch_path may be a str (single file) or a callable that
                # returns the current "bytes written so far" — useful for
                # the multi-file save_dataset case where the file path isn't
                # known upfront.
                if self.watch_path and self.timeout_s > 0:
                    try:
                        if callable(self.watch_path):
                            size = int(self.watch_path() or 0)
                        else:
                            size = os.path.getsize(self.watch_path)
                    except OSError:
                        size = 0
                    except Exception:
                        size = 0
                    if size > self._last_size:
                        self._last_size = size
                        self._last_progress_ts = time.monotonic()
                    elif time.monotonic() - self._last_progress_ts > self.timeout_s:
                        logger.warning(
                            f"  ⚠ {self.label}: no I/O progress detected for "
                            f"{self.timeout_s / 60:.0f} min on the rule's "
                            f"output directory. Stopping further heartbeats. "
                            f"No action taken — the worker is NOT killed and "
                            f"the rule is NOT aborted; if the body eventually "
                            f"completes the result is preserved. (A retry "
                            f"would only trigger if the body itself returned "
                            f"after this point; under the typical "
                            f"syscall-stuck scenario the body cannot return "
                            f"until SLURM walltime expires.) "
                            f"This message often appears for genuinely-slow "
                            f"compute-heavy rules where the dask graph runs "
                            f"longer than the watchdog timeout before the "
                            f"first byte is written."
                        )
                        self._timed_out = True
                        self._stop.set()
                        return

        self._th = threading.Thread(
            target=_tick, name=f"hb-{self.label}", daemon=True
        )
        self._th.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop.set()
        if self._th is not None:
            self._th.join(timeout=2)
        if self._t0 is not None:
            elapsed = time.monotonic() - self._t0
            if self._timed_out:
                # Watcher fired during execution, but the body returned
                # anyway — meaning the save eventually completed (or raised
                # its own exception). Either way, the data is in its final
                # state; raising SaveTimeout here would cause a *successful*
                # save to be re-attempted by the retry loop, double-writing
                # large files. Just note the late completion.
                status = "ok (after watchdog fired)" if exc_type is None else f"failed ({exc_type.__name__})"
                logger.info(f"  ✓ {self.label} done in {elapsed:.0f}s [{status}]")
            else:
                status = "ok" if exc_type is None else f"failed ({exc_type.__name__})"
                logger.info(f"  ✓ {self.label} done in {elapsed:.0f}s [{status}]")
        # NOTE on retry mechanism (PLAN §E): we used to raise SaveTimeout
        # from here when _timed_out and exc_type is None, but that path is
        # only ever taken AFTER the body completes (Python contract: __exit__
        # runs after the with-block body returns or raises). Under the
        # syscall-stuck failure mode the body never returns, so __exit__
        # never runs — raising from here was never going to help. And
        # under the slow-but-successful case the body returned with the
        # data saved, so raising would actively *break* a working write.
        # The retry loop in save_dataset still catches SaveTimeout if it
        # is raised explicitly by inner code (e.g., a future enhancement
        # using signal.alarm to interrupt the syscall), or any other
        # transient exception from _save_dataset_impl.
        return False


def _ensure_external_variables(ds):
    """CF 1.11 §7.2: announce cell_measures that live in a sibling fx file."""
    if not isinstance(ds, xr.Dataset):
        return ds
    external = _collect_external_cell_measures(ds)
    if not external:
        return ds
    existing = ds.attrs.get("external_variables", "")
    ds.attrs["external_variables"] = " ".join(sorted({*existing.split(), *external}))
    return ds


def _ensure_coordinates_attr(ds):
    """Rebuild ``coordinates`` attribute on each data var from current names.

    ``set_coordinate_attributes`` runs early in the pipeline (before
    ``map_dimensions``); a rename that happens afterwards (e.g. a vertical
    coord ``pressure_levels`` -> ``plev19``) would leave the stored string
    pointing at a variable that no longer exists. Regenerate at save time
    from the current dim/coord names so the attribute always matches what
    is actually in the file.
    """
    if not isinstance(ds, xr.Dataset):
        return ds
    for var_name in ds.data_vars:
        da = ds[var_name]
        if str(var_name).endswith(("_bnds", "_bounds")) or str(var_name).startswith("bounds_"):
            continue
        names = []
        for dim in da.dims:
            if dim in ds.coords and dim not in names:
                names.append(str(dim))
        for coord_name in da.coords:
            cn = str(coord_name)
            if cn not in names:
                names.append(cn)
        if names:
            da.encoding.pop("coordinates", None)
            da.attrs["coordinates"] = " ".join(names)
    return ds


def _strip_unportable_encoding(ds):
    """Drop encoding keys that vary by xarray backend engine and would
    otherwise propagate from the load engine into the save call, plus
    CF-incompatible leading-underscore attrs on data variables.

    Specifically: when the input was opened with ``engine="h5netcdf"``,
    coord variables (``lat``, ``lon``, ``time*``, etc.) get an
    ``encoding`` with ``compression="unknown"`` because h5netcdf doesn't
    recognise the BLOSC HDF5 filter (filter id 32001). The default
    netcdf4 backend instead reports ``blosc={...}``. xarray's
    ``to_netcdf`` then fails on save with
    ``ValueError("Unsupported value for compression kwarg ...")``.

    Also strips leading-underscore attrs from data variables (other than
    the netCDF-reserved ``_FillValue``) — CF §2.3 reserves the
    ``_``-prefix for netCDF internals, and quantize-bit-groom filters
    emit such attrs (e.g. ``_QuantizeBitGroomNumberOfSignificantDigits``).
    """
    if not isinstance(ds, xr.Dataset):
        return ds
    bad_keys = ("compression", "compression_opts")
    for name in list(ds.coords) + [v for v in ds.variables if v not in ds.data_vars]:
        var = ds.variables.get(name)
        if var is None:
            continue
        val = var.encoding.get("compression")
        if val in (None, "unknown") or val is False:
            for k in bad_keys:
                var.encoding.pop(k, None)
    # CF §2.3: data-var attribute names must not start with `_`. The
    # netCDF-reserved `_FillValue` is the one allowed exception.
    for vname in ds.data_vars:
        var = ds.variables.get(vname)
        if var is None:
            continue
        stale = [a for a in list(var.attrs) if a.startswith("_") and a != "_FillValue"]
        for a in stale:
            var.attrs.pop(a, None)
    return ds


_HORIZONTAL_COORD_ATTRS = {
    "lat":       {"standard_name": "latitude",  "long_name": "latitude",  "units": "degrees_north", "axis": "Y"},
    "latitude":  {"standard_name": "latitude",  "long_name": "latitude",  "units": "degrees_north", "axis": "Y"},
    "lon":       {"standard_name": "longitude", "long_name": "longitude", "units": "degrees_east",  "axis": "X"},
    "longitude": {"standard_name": "longitude", "long_name": "longitude", "units": "degrees_east",  "axis": "X"},
}

# Pairs where one is a renamed dim coord and the other is an auxiliary
# carry-over. Only the dim coord may declare ``axis`` / ``standard_name``
# to avoid the cf §5 "duplicate axis" mandatory finding.
_AXIS_PREFERRED = (("longitude", "lon"), ("latitude", "lat"))


def _ensure_horizontal_coord_attrs(ds):
    """Safety-net: guarantee CF attrs on horizontal coords + their bounds.

    Coords added after ``set_coordinate_attributes`` (e.g. by a regrid step)
    can miss ``standard_name``/``axis``/``units``. Also strips stale
    vertical-coord leftovers (``positive``, ``long_name`` mentioning
    "vertical", a stray ``name`` attr) and any per-variable attrs on the
    bounds variable (CF §7.1 — bounds inherit from the parent).
    """
    if not isinstance(ds, xr.Dataset):
        return ds

    # Identify which coord wins the axis/standard_name when a renamed
    # dim coord and an auxiliary copy coexist.
    demoted = set()
    for dim_name, aux_name in _AXIS_PREFERRED:
        if dim_name in ds.variables and aux_name in ds.variables:
            demoted.add(aux_name)

    for name, expected in _HORIZONTAL_COORD_ATTRS.items():
        if name not in ds.variables:
            continue
        attrs = ds[name].attrs
        # Strip vertical-coord leftovers regardless of who claimed this slot.
        attrs.pop("positive", None)
        attrs.pop("name", None)
        ln = attrs.get("long_name")
        if isinstance(ln, str) and "vertical" in ln.lower():
            attrs.pop("long_name", None)
        # Apply CF essentials; skip axis/standard_name on the demoted aux
        # copy to avoid duplicate-axis findings.
        for k, v in expected.items():
            if name in demoted and k in ("axis", "standard_name"):
                attrs.pop(k, None)
                continue
            attrs[k] = v
        bname = f"{name}_bnds"
        if bname in ds.variables:
            stale = [a for a in list(ds[bname].attrs) if a != "_FillValue"]
            for a in stale:
                ds[bname].attrs.pop(a, None)
    return ds


def _drop_xios_aux_time_coords(ds):
    """Drop NEMO/FESOM XIOS auxiliary time coords that don't belong in CMIP7.

    XIOS adds ``time_centered`` (and its companion ``time_centered_bounds``)
    as auxiliary time coordinates on monthly/daily-mean output, intended as
    a hint that the timestamp represents the centre of the averaging
    period. CMIP7 wants exactly one time coord (``time``) with one bounds
    variable (``time_bnds``); the extra coord causes:

    - wcrp_cmip7 ``[VAR004]`` — ``time_centered`` declares ``bounds=
      "time_centered_bounds"`` but pycmor's time_bounds step doesn't rebuild
      that bounds var, so it ends up dangling.
    - wcrp_cmip7 ``[TIME003a]`` — ``time_centered:calendar='standard'``
      survives the proleptic_gregorian override pycmor applies to the main
      ``time`` coord.

    Strip both unconditionally before save. If a future tier needs to keep
    a model-native time coord, replace this with a per-rule opt-out.
    """
    for aux in ("time_centered", "time_centered_bounds"):
        if aux in ds.variables:
            ds = ds.drop_vars(aux)
        elif aux in ds.coords:
            ds = ds.reset_coords(aux, drop=True)
    return ds


def _ensure_lat_lon_bounds_and_external_vars(ds, rule=None):
    """Wrap _ensure_lat_lon_bounds with post-passes that announce external
    cell_measures (CF 1.11 §7.2) and refresh the ``coordinates`` attr."""
    ds = _drop_xios_aux_time_coords(ds)
    ds = _ensure_lat_lon_bounds_impl(ds, rule)
    ds = _ensure_external_variables(ds)
    ds = _ensure_coordinates_attr(ds)
    ds = _ensure_horizontal_coord_attrs(ds)
    ds = _strip_unportable_encoding(ds)
    return ds


def _recover_bounds_from_inputs(ds, rule, coord_name, declared_bounds_name):
    """Pull a bounds variable from the first ``rule.inputs`` file when the
    live dataset has lost it (XIOS bounds carry an extra nvertex dim and
    are dropped by simple ``ds[var]`` variable selection)."""
    import numpy as np

    if rule is None:
        return None
    candidates = [n for n in (declared_bounds_name, f"bounds_{coord_name}", f"{coord_name}_bnds") if n]
    try:
        inputs = getattr(rule, "inputs", None) or []
        for input_collection in inputs:
            files = getattr(input_collection, "files", None) or []
            for file_path in files:
                try:
                    src = xr.open_dataset(str(file_path), decode_times=False)
                except Exception:
                    continue
                try:
                    for cand in candidates:
                        if cand not in src.variables:
                            continue
                        bvar = src[cand]
                        # Expect shape (n_cells, nvertex) aligned with coord length.
                        if bvar.ndim != 2 or bvar.shape[0] != ds[coord_name].size:
                            continue
                        cell_dim = ds[coord_name].dims[0]
                        vdim = bvar.dims[1]
                        # CF §7.1: bounds variables must not carry their own
                        # attributes (units, standard_name, ...) -- they inherit
                        # from the parent coord. Pass an empty attrs dict.
                        return xr.DataArray(
                            np.asarray(bvar.values),
                            dims=(cell_dim, vdim),
                            attrs={},
                        )
                finally:
                    src.close()
                # Only inspect the first file that opens; bounds are time-invariant.
                return None
    except Exception as e:
        logger.debug(f"  → bounds recovery for '{coord_name}' failed: {e}")
    return None


def _ensure_lat_lon_bounds_impl(ds, rule=None):
    """
    Add lat_bnds/lon_bnds to a dataset.

    For regular monotonic 1-D coords, bounds are inferred from cell centers.
    For unstructured (non-monotonic) coords, bounds are copied from
    ``rule.grid_file`` if it contains matching ``lat_bnds(ncells, vertices)`` /
    ``lon_bnds(ncells, vertices)``. Also recognises the XIOS naming convention
    ``bounds_<coord>`` used by IFS output and renames to the CF-standard
    ``<coord>_bnds`` form when present. Required for CMIP7 compliance (cchecker
    ATTR001).
    """
    import numpy as np

    if not isinstance(ds, xr.Dataset):
        return ds
    # Adopt XIOS-style `bounds_lat` / `bounds_lon` bounds if present (rename to
    # the CF-standard `<coord>_bnds` form and update the `bounds` attr). If the
    # referenced bounds variable was dropped during variable selection (XIOS
    # stores bounds as data_vars with an extra ``nvertex`` dim), try pulling
    # it from the first input file named by ``rule.inputs``.
    for name in ("lat", "latitude", "lon", "longitude"):
        if name not in ds.variables:
            continue
        cf_bname = f"{name}_bnds"
        xios_bname = f"bounds_{name}"
        if cf_bname not in ds.variables and xios_bname in ds.variables:
            ds = ds.rename({xios_bname: cf_bname})
            ds[name].attrs["bounds"] = cf_bname
            ds[cf_bname].encoding["_FillValue"] = None
            continue
        declared = ds[name].attrs.get("bounds")
        if declared and declared in ds.variables:
            continue
        # Declared bounds missing; try to re-attach from the first input file.
        if cf_bname in ds.variables:
            continue
        recovered = _recover_bounds_from_inputs(ds, rule, name, declared)
        if recovered is not None:
            ds[cf_bname] = recovered
            ds[name].attrs["bounds"] = cf_bname
            ds[cf_bname].encoding["_FillValue"] = None
            continue
        # Recovery failed and the canonical name still isn't in ds; if the
        # stale XIOS pointer ``bounds_lat`` / ``bounds_lon`` is still in the
        # attrs it would trip wcrp_cmip7 VAR004 ``Bounds variable 'bounds_lat'
        # referenced by 'lat' not found``. Drop the dangling pointer so the
        # file at least passes CF, even if the actual bnds variable is
        # missing (that's a separate ATTR001 finding handled per-rule).
        if declared and declared not in ds.variables and cf_bname not in ds.variables:
            ds[name].attrs.pop("bounds", None)
            ds[name].encoding.pop("bounds", None)
    # Prefer the mesh's polygon bnds over whatever was renamed/recovered above
    # when a ``rule.grid_file`` is configured. FESOM/XIOS writes
    # ``bounds_lat``/``bounds_lon`` truncated to nvertex=8 with many cells
    # collapsed to 1-2 unique vertices padded with the last value — degenerate
    # line / thin-triangle polygons whose bbox doesn't contain the stored
    # centroid. The full polygon (up to 16 vertices on DARS2) lives in
    # ``mesh.nc``. Drop the truncated lat_bnds/lon_bnds so the unstructured
    # branch below pulls the canonical mesh polygons via
    # ``_attach_bounds_from_mesh``. Skipped when no mesh is configured or the
    # mesh doesn't carry matching-size lat_bnds/lon_bnds.
    if rule is not None and getattr(rule, "grid_file", None):
        try:
            mesh_probe = xr.open_dataset(rule.grid_file, decode_times=False)
            try:
                coord_sizes = {ds[c].size for c in ("lat", "latitude", "lon", "longitude") if c in ds.variables}
                has_mesh_bnds = any(
                    v in mesh_probe.variables
                    and mesh_probe[v].ndim == 2
                    and mesh_probe[v].shape[0] in coord_sizes
                    for v in ("lat_bnds", "lon_bnds")
                )
            finally:
                mesh_probe.close()
            if has_mesh_bnds:
                dropped = []
                for stale in ("lat_bnds", "lon_bnds"):
                    if stale in ds.variables:
                        ds = ds.drop_vars(stale)
                        dropped.append(stale)
                for name in ("lat", "latitude", "lon", "longitude"):
                    if name in ds.variables:
                        ds[name].attrs.pop("bounds", None)
                logger.info(f"  → mesh-bnds-prefer: dropped {dropped} so mesh polygons are used")
        except Exception as e:
            logger.warning(f"  → mesh-bnds-prefer probe failed: {e}")
    regular = []
    unstructured = []
    for name in ("lat", "latitude", "lon", "longitude"):
        if name not in ds.variables:
            continue
        coord = ds[name]
        bname = f"{name}_bnds"
        if bname in ds.variables:
            continue
        if coord.ndim != 1 or coord.size < 2:
            continue
        try:
            vals = np.asarray(coord.values)
            diffs = np.diff(vals)
            if np.all(diffs > 0) or np.all(diffs < 0):
                regular.append(name)
            else:
                unstructured.append(name)
        except Exception:
            continue
    if regular:
        ds = add_bounds_from_coords(ds, coord_names=regular)
        for name in regular:
            bname = f"{name}_bnds"
            if bname in ds.variables:
                ds[bname].encoding["_FillValue"] = None
    if unstructured and rule is not None:
        ds = _attach_bounds_from_mesh(ds, rule, unstructured)

    # CMIP6/7 cmor-tables specify `type=double` (float64) for latitude /
    # longitude coordinate variables, and CMOR writes them that way by
    # default. FESOM/XIOS source files store lat/lon (and their bounds)
    # as float32. Without an explicit promotion here the ~0.7% of cells
    # whose centroid is a float32-quantum outside its own polygon trip
    # cf §7.1 ("coord outside bnds"). Promote both data and the encoded
    # on-disk dtype so it survives save_dataset's round-trip.
    for name in ("lat", "latitude", "lon", "longitude"):
        if name not in ds.variables:
            continue
        coord = ds[name]
        if coord.ndim != 1 or coord.size < 2:
            continue
        if str(coord.dtype) == "float64":
            # Already double — make sure encoding agrees but skip the cast.
            ds[name].encoding["dtype"] = "float64"
        else:
            promoted = xr.DataArray(
                coord.values.astype(np.float64, copy=False),
                dims=coord.dims,
                attrs=dict(coord.attrs),
            )
            promoted.encoding = dict(coord.encoding)
            promoted.encoding["dtype"] = "float64"
            promoted.encoding["_FillValue"] = None
            ds = ds.assign_coords({name: promoted})
        bname = f"{name}_bnds"
        if bname in ds.variables:
            bvar = ds[bname]
            if str(bvar.dtype) != "float64":
                new_b = xr.DataArray(
                    bvar.values.astype(np.float64, copy=False),
                    dims=bvar.dims,
                    attrs=dict(bvar.attrs),
                )
                new_b.encoding = dict(bvar.encoding)
                ds[bname] = new_b
            ds[bname].encoding["dtype"] = "float64"
            ds[bname].encoding["_FillValue"] = None

    # cf §7.1 + dateline normalisation for longitude.
    #
    # FESOM unstructured triangles crossing the dateline ship vertices on
    # BOTH branches (e.g. (179, -179, -180)) while FESOM's computed
    # element centroid stores ``lon`` in just one branch. wcrp/cf §7.1
    # then sees centroid outside the [min, max] vertex bbox even though
    # the geometry is correct on the sphere. The cli72 / cli73 "1814
    # point(s) lie outside lon_bnds" finding on difmxylo / tauuo / tauvo
    # / sistressave is exactly this — dateline-crossing triangles, not
    # float-precision drift (both lat and lon are already float64; lat
    # passes because it doesn't wrap).
    #
    # Fix: shift each vertex into the 360° window centred on the
    # centroid. This is identity-on-the-sphere; vertices stay near the
    # canonical range (a few touch 181° or -181° at the dateline, which
    # CF doesn't forbid), and the bbox now contains the centroid by
    # construction. Vectorised so the 6.2M-elem 3D files don't churn
    # Python.
    for name in ("lon", "longitude"):
        if name not in ds.variables:
            continue
        bname = f"{name}_bnds"
        if bname not in ds.variables:
            continue
        coord = ds[name]
        bnds = ds[bname]
        if coord.ndim != 1 or bnds.ndim != 2 or bnds.shape[0] != coord.size:
            continue
        try:
            cv = np.asarray(coord.values, dtype=np.float64)
            bv = np.asarray(bnds.values, dtype=np.float64)
            shifted = bv - 360.0 * np.round((bv - cv[:, np.newaxis]) / 360.0)
            if not np.array_equal(shifted, bv):
                logger.info(
                    f"  → dateline normalise: shifted {int((shifted != bv).any(axis=1).sum())} "
                    f"of {bv.shape[0]} {bname} rows into the 360-window of the centroid"
                )
                new_b = xr.DataArray(
                    shifted,
                    dims=bnds.dims,
                    attrs=dict(bnds.attrs),
                )
                new_b.encoding = dict(bnds.encoding)
                new_b.encoding["dtype"] = "float64"
                new_b.encoding["_FillValue"] = None
                ds[bname] = new_b
        except Exception as exc:
            logger.warning(
                f"  → dateline normalise on {bname} failed: {exc}; "
                f"leaving bnds unchanged"
            )

    return ds


def _attach_bounds_from_mesh(ds, rule, coord_names):
    """Copy ``lat_bnds``/``lon_bnds`` from ``rule.grid_file`` if dimensions match.

    Used for unstructured meshes (e.g. FESOM2) where cell vertices cannot be
    inferred from node positions alone; the mesh/griddes NetCDF holds pre-
    computed dual-cell vertex coordinates.
    """
    import numpy as np

    grid_file = getattr(rule, "grid_file", None)
    if not grid_file:
        return ds
    try:
        mesh = xr.open_dataset(grid_file, decode_times=False)
    except Exception as e:
        logger.debug(f"  → Skipping mesh bounds: cannot open {grid_file}: {e}")
        return ds
    try:
        for name in coord_names:
            bname = f"{name}_bnds"
            mesh_bname = "lat_bnds" if name in ("lat", "latitude") else "lon_bnds"
            if mesh_bname not in mesh.variables:
                continue
            mb = mesh[mesh_bname]
            coord = ds[name]
            if coord.size != mb.shape[0]:
                logger.debug(
                    f"  → Skipping mesh bounds for '{name}': size mismatch "
                    f"{coord.size} vs {mb.shape[0]}"
                )
                continue
            # Verify values agree so we aren't pulling bounds from a different mesh.
            mesh_centers_name = "lat" if name in ("lat", "latitude") else "lon"
            if mesh_centers_name in mesh.variables:
                # Tolerance covers float32 vs float64 representation of the same mesh
                if not np.allclose(
                    np.asarray(coord.values, dtype=float),
                    np.asarray(mesh[mesh_centers_name].values, dtype=float),
                    rtol=0,
                    atol=1e-4,
                ):
                    logger.debug(
                        f"  → Skipping mesh bounds for '{name}': centers disagree with mesh"
                    )
                    continue
            # Rename the mesh vertex dim to match the variable's spatial dim.
            # CF §7.1: bounds variables must not carry their own attributes
            # (they inherit from the parent coord); pass an empty attrs dict.
            #
            # Force float64 on BOTH the coord and the bnds. The DARS mesh
            # files store lat/lon as float32; promoting at this layer
            # gives the CF §7.1 in-bounds check enough precision to
            # tolerate the ULP-level drift on the ~0.7% of cells where
            # float32 puts the centroid a hair outside its polygon. Same
            # geometric truth, more decimals.
            dim_name = coord.dims[0]
            vdim = mb.dims[1]
            data = mb.values.astype(np.float64, copy=False)
            ds[bname] = xr.DataArray(
                data,
                dims=(dim_name, vdim),
                attrs={},
            )
            ds[bname].encoding["_FillValue"] = None
            # In-memory cast above is not enough — xarray's write path uses
            # ``encoding["dtype"]`` to pick the on-disk type and will downcast
            # back to float32 if the encoding inherited from the source file
            # says so. Force float64 explicitly so what we write matches what
            # the mesh actually contains. CMOR's de facto convention is
            # double-precision spatial coords; the 21k+ cf §7.1 outliers on
            # DARS2 are quantum-level float32 drift, not real geometry.
            ds[bname].encoding["dtype"] = "float64"
            mesh_centers = mesh[mesh_centers_name]
            new_coord = xr.DataArray(
                mesh_centers.values.astype(np.float64, copy=False),
                dims=(dim_name,),
                attrs=dict(ds[name].attrs),
            )
            new_coord.attrs["bounds"] = bname
            new_coord.encoding["_FillValue"] = None
            new_coord.encoding["dtype"] = "float64"
            ds = ds.assign_coords({name: new_coord})
    finally:
        mesh.close()
    return ds


def _is_dask_backed(ds):
    """Check if any variable in a dataset/dataarray is backed by dask arrays."""
    if isinstance(ds, xr.DataArray):
        return ds.chunks is not None
    return any(v.chunks is not None for v in ds.data_vars.values())


def _graph_metrics(ds_or_da):
    """Cheap measurement of a dask-backed Dataset/DataArray's task graph
    for instrumentation. Returns ``(n_keys, n_layers, approx_bytes,
    n_chunks)`` or ``None`` on any failure. Designed to be O(layers),
    not O(keys), so it's safe to call inline on huge graphs.

    Used by the GRAPH_METRIC / GRAPH_RESULT log records that the
    ``examples/analyze_graph_metrics.py`` aggregator parses.
    """
    try:
        g = ds_or_da.__dask_graph__()
    except Exception:
        return None
    try:
        n_keys = len(g)
    except Exception:
        n_keys = None
    try:
        layers = getattr(g, "layers", None)
        n_layers = len(layers) if layers is not None else 1
    except Exception:
        n_layers = None
    try:
        if layers is not None:
            approx_bytes = sum(sys.getsizeof(layer) for layer in layers.values())
        else:
            approx_bytes = sys.getsizeof(g)
    except Exception:
        approx_bytes = None
    try:
        # Total chunk count across the array(s).
        if hasattr(ds_or_da, "chunks"):
            chunks = ds_or_da.chunks
            if isinstance(chunks, dict):
                # xr.Dataset.chunks → dict[dim] = tuple of chunk sizes
                n_chunks = 1
                for cs in chunks.values():
                    n_chunks *= max(1, len(cs))
            elif chunks:
                # DataArray.chunks → tuple of (chunk-size-tuple, ...) per dim
                n_chunks = 1
                for cs in chunks:
                    n_chunks *= max(1, len(cs))
            else:
                n_chunks = None
        else:
            n_chunks = None
    except Exception:
        n_chunks = None
    return n_keys, n_layers, approx_bytes, n_chunks


_LIBC_TRIM = None


def _trim_malloc_arenas():
    """Force glibc to release unused arena pages back to the OS.
    Called between rules in a shard to prevent the fragmentation pattern
    that killed cli19/cli30 lrcs_seaice: after ~15 rules each materializing
    ~14 GiB numpy arrays, glibc's heap fragments and a subsequent 4 MiB
    allocation fails despite ~300 GiB of free cgroup memory.

    No-op on non-Linux. Logs failures at debug level only — this is
    best-effort cleanup, not load-bearing.
    """
    global _LIBC_TRIM
    try:
        if _LIBC_TRIM is None:
            import ctypes
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            _LIBC_TRIM = libc.malloc_trim
            _LIBC_TRIM.argtypes = [ctypes.c_size_t]
            _LIBC_TRIM.restype = ctypes.c_int
        import gc
        gc.collect()
        _LIBC_TRIM(0)
    except Exception as exc:
        logger.debug(f"_trim_malloc_arenas: {type(exc).__name__}: {exc}")


def _add_cf_quantization_metadata(ds, rule):
    """Declare lossy quantization the way CF 1.12 section 8.4 requires.

    netCDF-C writes its own ``_QuantizeBitGroomNumberOfSignificantDigits``
    marker when quantization is enabled, but that is a library artefact,
    not CF metadata. CF 1.12 wants provenance instead:

    - a *quantization container variable* carrying string ``algorithm``
      and ``implementation`` attributes,
    - a string ``quantization`` attribute on each quantized variable
      naming that container,
    - an integer ``quantization_nsd`` on each quantized variable
      (``quantization_nsb`` instead, for the ``bitround`` algorithm).

    NSD must satisfy 1 <= NSD <= 7 for float and <= 15 for double; a value
    outside that range is skipped rather than written invalid.

    Raised in the DKRZ review of cli108: we shipped the netCDF-C marker
    alone, so the files did not say which algorithm produced them.
    """
    quantize_mode = "BitGroom"
    if hasattr(rule, "netcdf_quantize_mode"):
        quantize_mode = rule.netcdf_quantize_mode
    if not quantize_mode:
        return ds
    nsd = getattr(rule, "netcdf_significant_digits", 5)
    if not nsd:
        return ds

    algorithm = str(quantize_mode).lower()
    is_nsb = algorithm == "bitround"
    attr_name = "quantization_nsb" if is_nsb else "quantization_nsd"

    container = "quantization_info"
    if container not in ds.variables:
        try:
            import netCDF4 as _nc4
            impl = f"netCDF-C version {_nc4.__netcdf4libversion__}"
        except Exception:
            impl = "netCDF-C"
        # Plain data variable, NOT a coordinate: assign_coords would make
        # xarray list the container in every variable's ``coordinates``
        # attribute (and in the global one), which is wrong. The container
        # is just a metadata holder.
        ds[container] = xr.DataArray(np.int8(0), attrs={"algorithm": algorithm, "implementation": impl})
        ds[container].encoding["dtype"] = "int8"
        ds[container].encoding["_FillValue"] = None

    for var in ds.data_vars:
        da = ds[var]
        if str(var) == container or da.dtype.kind != "f":
            continue
        name = str(var)
        if name.endswith(("_bnds", "_bounds")) or name.startswith("bounds_"):
            continue
        limit = 7 if da.dtype.itemsize <= 4 else 15
        if is_nsb:
            limit = 23 if da.dtype.itemsize <= 4 else 52
        if not (1 <= int(nsd) <= limit):
            logger.warning(
                f"  {attr_name}={nsd} out of CF range 1..{limit} for {name!r} "
                f"({da.dtype}); not declaring quantization metadata"
            )
            continue
        da.attrs["quantization"] = container
        da.attrs[attr_name] = np.int32(int(nsd))

    return ds


def _safe_to_netcdf(ds_or_da, *args, scheduler="synchronous", **kwargs):
    """Wrapper around ``to_netcdf`` that:

    1. (Fix #3 of PLAN_save_dataset_reliability / FORENSIC_lrcs_seaice)
       Dispatches the **lazy compute** to the LocalCluster workers via
       ``Client.compute(..., sync=True)`` so the heavy regrid/mask/
       arithmetic happens on workers, not in the driver process.
       After compute, the result is an eager numpy-backed Dataset
       which is written via the regular ``to_netcdf`` path — no dask
       graph, no HLG pickle bug.

       Without this, every concurrent rule's full lazy graph (plus its
       intermediate buffers) accumulates in driver RSS when
       ``netcdf_write_scheduler: synchronous`` is set (cli16: 87 GiB
       driver RSS at 4 concurrent OIFS-regrid rules → cascade failure).

    2. Falls back to the legacy synchronous path
       (``to_netcdf(compute=False)`` → ``delayed.compute()`` under
       ``scheduler="synchronous"``) when no Client is active.

    3. For eager input (numpy-backed): direct ``to_netcdf`` — no
       dask graph is built, no serialization happens.

    Historical context for the synchronous workaround:
    ``TypeError: Could not serialize object of type _HLGExprSequence``
    /  ``cannot pickle '_thread.lock' object`` — the netCDF4 store's
    writer-lock isn't picklable, so dispatching the array-store dask
    graph through a Client failed. The new ``compute-then-write``
    pattern dodges that bug entirely because the writer is never in
    the graph that gets shipped to workers; only the compute is.

    See: dask/distributed#780, pydata/xarray#4406, dask/dask#10238,
    FORENSIC_lrcs_seaice_failure.md §"Fix #3", PLAN_save_dataset_reliability.md.
    """
    # cf Appendix A: ``coordinates`` is a data-variable attribute and must
    # not appear as a global. xarray emits one whenever a *coordinate* is
    # not referenced by any data variable, which is always true of
    # time_bnds, so every file carried ``:coordinates = "time_bnds"`` and
    # the cf-checker reported it as an error (DKRZ cli108 review).
    #
    # Setting ``encoding["coordinates"] = None`` is the usual advice and
    # does NOT work; verified directly against xarray:
    #
    #   baseline                    global coordinates attr: True
    #   ds.encoding["coordinates"]=None                      True
    #   v.encoding["coordinates"]=None                       True
    #   ds.reset_coords(...)                                 False
    #
    # Demoting the bounds to plain data variables is what actually
    # suppresses it, and is also the CF-correct shape: a bounds variable
    # is reached through ``time:bounds``, it is not itself a coordinate.
    # Done here because this is the single choke point every write passes
    # through; several upstream fixups return fresh objects and would drop
    # anything set earlier.
    try:
        if hasattr(ds_or_da, "coords"):
            _bnds = [
                c for c in ds_or_da.coords
                if str(c).endswith(("_bnds", "_bounds")) or str(c).startswith("bounds_")
            ]
            if _bnds:
                ds_or_da = ds_or_da.reset_coords(_bnds)
            # cf 7.1: a bounds variable carries no attributes of its own.
            # xarray would give it a ``coordinates`` listing any scalar coord
            # in the dataset (e.g. the tile ``type``); suppress that.
            for _b in _bnds:
                if _b in getattr(ds_or_da, "variables", {}):
                    ds_or_da[_b].encoding["coordinates"] = None
    except Exception as _exc:  # pragma: no cover - defensive
        logger.debug(f"could not demote bounds coords before write: {_exc}")

    # Identify rule for GRAPH_METRIC log records. Best effort — uses the
    # DataArray's .name attribute, or first data_var for a Dataset.
    try:
        if hasattr(ds_or_da, "name") and ds_or_da.name:
            rule_id = str(ds_or_da.name)
        elif hasattr(ds_or_da, "data_vars"):
            rule_id = next(iter(ds_or_da.data_vars), "?")
        else:
            rule_id = "?"
    except Exception:
        rule_id = "?"

    if not _is_dask_backed(ds_or_da):
        # Eager input: no dask graph, no serialization. Just write.
        logger.info(f"GRAPH_METRIC rule={rule_id} backend=eager nodes=0 layers=0 bytes=0 chunks=0")
        t0 = time.time()
        result = ds_or_da.to_netcdf(*args, **kwargs)
        logger.info(f"GRAPH_RESULT rule={rule_id} backend=eager status=ok elapsed_s={time.time()-t0:.2f}")
        _trim_malloc_arenas()
        return result

    # Measure the lazy graph (cheap — O(layers), not O(keys)).
    metrics = _graph_metrics(ds_or_da)
    if metrics is not None:
        n_keys, n_layers, approx_bytes, n_chunks = metrics
    else:
        n_keys = n_layers = approx_bytes = n_chunks = None

    # Try the Fix #3 path: gather data via workers, then write eagerly.
    use_worker_compute = os.environ.get("PYCMOR_WORKER_COMPUTE", "auto").lower()
    if use_worker_compute != "off":
        try:
            from dask.distributed import get_client
            client = get_client()
        except (ImportError, ValueError):
            client = None
        if client is not None:
            logger.info(
                f"GRAPH_METRIC rule={rule_id} backend=worker_compute "
                f"nodes={n_keys} layers={n_layers} bytes={approx_bytes} chunks={n_chunks}"
            )
            t0 = time.time()
            try:
                eager = client.compute(ds_or_da, sync=True)
                # Eager Dataset/DataArray now backed by numpy -- the
                # regular to_netcdf path doesn't build a dask graph.
                eager.to_netcdf(*args, **kwargs)
                logger.info(
                    f"GRAPH_RESULT rule={rule_id} backend=worker_compute "
                    f"status=ok elapsed_s={time.time()-t0:.2f}"
                )
                del eager
                _trim_malloc_arenas()
                return None
            except Exception as exc:
                logger.warning(
                    f"GRAPH_RESULT rule={rule_id} backend=worker_compute "
                    f"status=fallback elapsed_s={time.time()-t0:.2f} exc={type(exc).__name__}"
                )
                logger.warning(
                    f"_safe_to_netcdf: Client.compute path failed "
                    f"({type(exc).__name__}: {exc}); falling back to "
                    f"synchronous scheduler. Set PYCMOR_WORKER_COMPUTE=off "
                    f"to skip this path entirely."
                )

    # Legacy / fallback: build the lazy write graph and execute it
    # in-process via the synchronous scheduler. Driver-bytes-through
    # behaviour, but doesn't OOM the worker pool and survives the
    # HLG pickle bug.
    logger.info(
        f"GRAPH_METRIC rule={rule_id} backend=sync "
        f"nodes={n_keys} layers={n_layers} bytes={approx_bytes} chunks={n_chunks}"
    )
    t0 = time.time()
    delayed = ds_or_da.to_netcdf(*args, compute=False, **kwargs)
    with dask.config.set(scheduler=scheduler):
        delayed.compute()
    logger.info(f"GRAPH_RESULT rule={rule_id} backend=sync status=ok elapsed_s={time.time()-t0:.2f}")
    _trim_malloc_arenas()
    return None


def _is_tmpfs(path):
    """True iff ``path`` is mounted as tmpfs. Reads ``/proc/mounts``;
    Linux-only (fine for HPC and CI; returns False on macOS/Windows)."""
    try:
        with open("/proc/mounts") as fh:
            mounts = [line.split() for line in fh]
    except OSError:
        return False
    # Walk up the path until we find the longest matching mount point.
    target = os.path.abspath(path)
    best_fstype = None
    best_len = -1
    for parts in mounts:
        if len(parts) < 3:
            continue
        mountpoint, fstype = parts[1], parts[2]
        if (target == mountpoint or target.startswith(mountpoint.rstrip("/") + "/")) and len(mountpoint) > best_len:
            best_fstype = fstype
            best_len = len(mountpoint)
    return best_fstype == "tmpfs"


# Module-level cache for the auto-detect path of _tmpfs_staging_available.
# Cleared in tests via _reset_tmpfs_cache(). Production: filled once at first
# call; filesystem identity doesn't change within a run.
_TMPFS_STAGING_CACHE = {}


def _reset_tmpfs_cache():
    """Clear the auto-detect cache. Test helper; never call in production."""
    _TMPFS_STAGING_CACHE.clear()


def _tmpfs_staging_available(rule=None):
    """Return True iff three-stage atomic-write staging via tmpfs is safe.

    Resolution order (first match wins):

    1. Env ``PYCMOR_TMPFS_STAGING=off`` → False (force off).
    2. Env ``PYCMOR_TMPFS_STAGING=on``  → True (skip auto-detect; still
       respects per-rule opt-out).
    3. Per-rule ``netcdf_tmpfs_staging: false`` → False (rule opt-out).
    4. Env ``PYCMOR_TMPFS_STAGING=auto`` (default) → auto-detect:
       ``/tmp`` is tmpfs AND has at least ``PYCMOR_TMPFS_MIN_FREE_GB``
       (default 4 GB) free.

    Auto-detect result is cached at module level (first call wins, the
    filesystem identity / mount won't change during a run).

    Rule opt-out is checked on every call (each rule may differ).
    """
    mode = os.environ.get("PYCMOR_TMPFS_STAGING", "auto").lower()
    if mode == "off":
        return False
    if mode == "on":
        return _rule_allows_tmpfs_staging(rule)
    # mode == "auto"
    if "auto_ok" not in _TMPFS_STAGING_CACHE:
        tmpdir = os.environ.get("PYCMOR_TMPFS_DIR", "/tmp")
        try:
            st = os.statvfs(tmpdir)
            free_gb = (st.f_bavail * st.f_frsize) / 1e9
        except OSError:
            _TMPFS_STAGING_CACHE["auto_ok"] = False
            logger.warning(
                f"tmpfs staging disabled: cannot statvfs({tmpdir!r}); "
                f"falling back to direct writes."
            )
            return False
        is_tmpfs_mount = _is_tmpfs(tmpdir)
        try:
            min_free_gb = float(os.environ.get("PYCMOR_TMPFS_MIN_FREE_GB", "4"))
        except (TypeError, ValueError):
            min_free_gb = 4.0
        ok = is_tmpfs_mount and free_gb >= min_free_gb
        if not ok:
            logger.warning(
                f"tmpfs staging disabled: {tmpdir!r} tmpfs={is_tmpfs_mount} "
                f"free={free_gb:.1f}GB (need tmpfs and ≥{min_free_gb}GB); "
                f"falling back to direct writes."
            )
        else:
            logger.info(
                f"tmpfs staging enabled: {tmpdir!r} tmpfs ({free_gb:.1f}GB free)."
            )
        _TMPFS_STAGING_CACHE["auto_ok"] = ok
    if not _TMPFS_STAGING_CACHE["auto_ok"]:
        return False
    return _rule_allows_tmpfs_staging(rule)


def _rule_allows_tmpfs_staging(rule):
    """Return False iff the rule explicitly sets ``netcdf_tmpfs_staging: false``."""
    if rule is None:
        return True
    try:
        val = rule.get("netcdf_tmpfs_staging") if hasattr(rule, "get") else getattr(rule, "netcdf_tmpfs_staging", None)
    except Exception:
        val = None
    if val is None:
        return True
    if isinstance(val, str):
        return val.lower() not in ("false", "off", "no", "0")
    return bool(val)


def _atomic_to_netcdf(ds_or_da, final_path, *args, rule=None, scheduler="synchronous", **kwargs):
    """Three-stage atomic write:

    1. Write the netCDF to node-local tmpfs (``/tmp``). Fast; no
       Lustre POSIX write-lock contention during the slow incremental
       HDF5 write.
    2. Copy from tmpfs to the target Lustre directory as
       ``<final_path>.tmp``. Single linear write; brief, predictable
       lock holds.
    3. ``os.rename(<final_path>.tmp, <final_path>)`` — atomic same-FS
       rename, metadata-only. The final path never has partial content
       visible to readers.

    Falls back to a direct ``_safe_to_netcdf(final_path)`` write if
    tmpfs staging is unavailable (see ``_tmpfs_staging_available``).

    Round-2 design — see ``PLAN_save_dataset_reliability.md`` and
    ``REVIEW_save_dataset_reliability_round1.md`` for the why and the
    correctness argument for the three-stage path (round 1's
    ``shutil.move`` was not atomic across filesystems).
    """
    import shutil
    import tempfile

    if not _tmpfs_staging_available(rule):
        return _safe_to_netcdf(ds_or_da, final_path, *args, scheduler=scheduler, **kwargs)

    tmpdir = os.environ.get("PYCMOR_TMPFS_DIR", "/tmp")
    fd, tmp_path = tempfile.mkstemp(
        dir=tmpdir, prefix=os.path.basename(final_path) + ".", suffix=".tmp"
    )
    os.close(fd)
    stage_path = final_path + ".tmp"
    try:
        # Stage 1: tmpfs write (fast, no Lustre lock contention)
        result = _safe_to_netcdf(ds_or_da, tmp_path, *args, scheduler=scheduler, **kwargs)
        # Stage 2: bounded copy to target FS at .tmp suffix (visible during copy,
        # but not at final_path)
        shutil.copy2(tmp_path, stage_path)
        os.unlink(tmp_path)
        # Stage 3: same-FS atomic rename
        os.rename(stage_path, final_path)
        return result
    except Exception:
        # Best-effort cleanup of both staging locations
        for p in (tmp_path, stage_path):
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
            except OSError as cleanup_exc:
                logger.warning(f"cleanup of {p!r} failed: {cleanup_exc!r}")
        raise


def _get_write_scheduler(rule):
    """Return the dask scheduler to use around xr.save_mfdataset.

    Default is ``"synchronous"`` — safe with any HDF5 build, but serialises
    zlib compression and caps throughput at single-thread speed (typically
    10–30 MB/s) for large compressed outputs.

    Override to ``"threads"`` (much faster on thread-safe HDF5 builds) via:

    * rule attribute ``netcdf_write_scheduler``, or
    * pycmor config key ``netcdf_write_scheduler``.
    """
    val = rule.get("netcdf_write_scheduler") if hasattr(rule, "get") else None
    if not val and hasattr(rule, "_pycmor_cfg"):
        try:
            val = rule._pycmor_cfg("netcdf_write_scheduler")
        except Exception:
            val = None
    return val or "synchronous"


def _encoding_from_dask_chunks(ds, rule):
    """
    Build netCDF encoding that matches existing dask chunks.

    Aligning netCDF chunks with dask chunks avoids expensive rechunking
    and makes the write a pure stream: each dask task writes exactly one
    netCDF chunk with zero read amplification.
    """
    compression_level = rule._pycmor_cfg("netcdf_compression_level")
    compression_level = getattr(rule, "netcdf_compression_level", compression_level)
    enable_compression = rule._pycmor_cfg("netcdf_enable_compression")
    enable_compression = getattr(rule, "netcdf_enable_compression", enable_compression)
    compression_codec = getattr(rule, "netcdf_compression_codec", None) or "zlib"
    # Defaults: BitGroom-5 is active for all float data variables unless
    # a rule/inherit block explicitly sets ``netcdf_quantize_mode: null``
    # (or an unset sig-digits) to opt out. Bounds / coord variables are
    # always skipped below.
    quantize_mode = "BitGroom"
    if hasattr(rule, "netcdf_quantize_mode"):
        quantize_mode = rule.netcdf_quantize_mode  # may be None to opt out
    significant_digits = getattr(rule, "netcdf_significant_digits", 5)

    encoding = {}
    for var in ds.data_vars:
        var_encoding = {}
        da = ds[var]
        if da.chunks is not None:
            # Use the max chunk size per dimension (chunks may be uneven at boundaries)
            chunksizes = tuple(max(c) for c in da.chunks)
            # wcrp FILE004d requires each data-variable chunk to be at least
            # 4 MiB uncompressed (a CMIP7 storage convention; smaller chunks
            # mean too many chunks → high metadata overhead). Dask-aligned
            # chunks on FESOM unstructured high-res grids (e.g. sfx, (12,
            # 18724)) end up at ~1.8 MiB and trip the check. cmip7repack is
            # supposed to fix this post-hoc but on 2D high-res fields it
            # re-uses the same shape — see cli71 sidecars. Enforce the
            # floor here by enlarging the LAST (rightmost, typically
            # horizontal) dim until the product crosses 4 MiB, capped at
            # the dim size. Other dims are left alone so the time-axis
            # chunking pycmor picked earlier is preserved.
            try:
                FOUR_MIB = 4 * 1024 * 1024
                dim_names = list(da.dims)
                dim_sizes = [ds.sizes[d] for d in dim_names]
                wordsize = da.dtype.itemsize
                from math import prod as _prod
                cur_bytes = _prod(chunksizes) * wordsize
                if cur_bytes < FOUR_MIB and len(chunksizes) > 0:
                    chunksizes = list(chunksizes)
                    # Grow the last dim's chunk until the chunk is >= 4 MiB
                    # (or we hit the full dim size).
                    last_idx = len(chunksizes) - 1
                    other_bytes = _prod(chunksizes[:-1]) * wordsize if last_idx > 0 else wordsize
                    needed_last = -(-FOUR_MIB // max(1, other_bytes))  # ceil-div
                    new_last = max(chunksizes[-1], min(dim_sizes[-1], needed_last))
                    if new_last != chunksizes[-1]:
                        logger.info(
                            f"chunk-floor: var {var!r} dask chunk "
                            f"{tuple(chunksizes)} = {cur_bytes} B < 4 MiB; "
                            f"growing {dim_names[-1]} {chunksizes[-1]} -> {new_last}"
                        )
                        chunksizes[-1] = new_last
                    chunksizes = tuple(chunksizes)
            except Exception as _exc:
                logger.warning(
                    f"chunk-floor: could not enforce 4 MiB minimum for {var!r}: {_exc}"
                )
            var_encoding["chunksizes"] = chunksizes
        if enable_compression:
            if compression_codec == "zlib":
                var_encoding["zlib"] = True
                var_encoding["complevel"] = compression_level
                var_encoding["shuffle"] = True
            else:
                var_encoding["compression"] = compression_codec
                var_encoding["complevel"] = compression_level
                if compression_codec.startswith("blosc"):
                    var_encoding["blosc_shuffle"] = 1
                elif compression_codec == "zstd":
                    var_encoding["shuffle"] = True
        # Lossy bit-level quantization (libnetcdf >= 4.9). Only apply to
        # float data variables; skip integer flag/index vars (bit-exact)
        # and bounds/coord variables (CF requires exact values).
        _var_name = str(var)
        _is_bounds_var = (
            _var_name.endswith(("_bnds", "_bounds"))
            or _var_name.startswith("bounds_")
        )
        if (
            quantize_mode
            and significant_digits
            and da.dtype.kind == "f"
            and not _is_bounds_var
        ):
            var_encoding["quantize_mode"] = quantize_mode
            var_encoding["significant_digits"] = int(significant_digits)
        # CF forbids _FillValue on bounds variables; respect explicit None and
        # skip *_bnds / *_bounds. For data variables, set the CMIP-required
        # 1.0e20 fill (xarray's default for float32 is NaN otherwise).
        _sentinel = object()
        _pre = da.encoding.get("_FillValue", _sentinel)
        _is_bounds = str(var).endswith(("_bnds", "_bounds")) or str(var).startswith(("bounds_",))
        if _pre is None or _is_bounds:
            var_encoding["_FillValue"] = None
        else:
            var_encoding["_FillValue"] = 1.0e20
        encoding[var] = var_encoding

    # CF §2.5.1: coordinate variables (lat, lon, time, lev, plev, ...) must
    # not have _FillValue. xarray's default for float coords is NaN, which
    # the netCDF library serialises as _FillValue=NaN — flagged by cchecker
    # on every areacella/areacello/fx file. Explicit None here suppresses
    # both the attr and the encoded fill.
    for cname in ds.coords:
        encoding.setdefault(str(cname), {})["_FillValue"] = None

    logger.info(f"Using dask-aligned netCDF chunks: {encoding.get(list(ds.data_vars)[0], {}).get('chunksizes', 'none')}")
    return encoding


def _filename_time_range(ds, rule) -> str:
    """
    Determine the time range used in naming the file.

    Parameters
    ----------
    ds : xarray.Dataset
        The input dataset.
    rule : Rule
        The rule object containing information for generating the
        filepath.

    Returns
    -------
    str
        time_range in filepath.
    """
    if not has_time_axis(ds):
        return ""
    time_label = get_time_label(ds)
    if is_scalar(ds[time_label]):
        return ""
    # Filename token is built from the ``time`` coordinate values (not
    # from ``time_bnds``) per CMIP7 Appendix 1 and CMOR practice. Earlier
    # revs derived it from bnds edges: bnds[-1, 1] slid one period past
    # coverage (cli96 522 TIME003 findings), bnds[-1, 0] matched the
    # pre-#62 checker convention but shipped ``..2300`` for 1hr tavg
    # where Appendix 1 (Martin Schupfner, 2026-07-06) and cc-plugin-wcrp
    # #62 (sol1105) both want the midpoint stamp ``..2330``. Use the
    # stamp directly: ``strftime`` truncates to the frequency's precision
    # (mon: %Y%m, day: %Y%m%d, 1hr: %Y%m%d%H%M, ...), which lines up with
    # canonical midpointed tavg and canonical instantaneous tpt files.
    start = pd.Timestamp(str(ds[time_label].data[0]))
    end = pd.Timestamp(str(ds[time_label].data[-1]))
    frequency_str = rule.data_request_variable.frequency
    if frequency_str in ("yr", "yrPt", "dec"):
        return f"{start.year:04d}-{end.year:04d}"                    # YYYY
    if frequency_str in ("mon", "monC", "monPt"):
        return f"{start:%Y%m}-{end:%Y%m}"                            # YYYYMM
    if frequency_str == "day":
        return f"{start:%Y%m%d}-{end:%Y%m%d}"                        # YYYYMMDD
    if frequency_str in ("6hr", "3hr", "1hr", "6hrPt", "3hrPt", "1hrPt", "1hrCM"):
        return f"{start:%Y%m%d%H%M}-{end:%Y%m%d%H%M}"                # YYYYMMDDhhmm
    if frequency_str in ("subhr", "subhrPt"):
        return f"{start:%Y%m%d%H%M%S}-{end:%Y%m%d%H%M%S}"            # YYYYMMDDhhmmss
    if frequency_str == "fx":
        return ""
    else:
        raise NotImplementedError(f"No implementation for {frequency_str} yet.")


def _sanitize_component(component):
    """
    Sanitize filename components to comply with CMIP6 specification.

    CMIP6 spec: All strings in filename use only: a-z, A-Z, 0-9, and hyphen (-)

    Parameters
    ----------
    component : str or Mock
        The component to sanitize

    Returns
    -------
    str
        The sanitized component
    """
    import re

    # Convert component to string if it's not already (handles Mock objects)
    if not isinstance(component, str):
        component = str(component)

    # Replace periods, underscores, and spaces with hyphens
    component = re.sub(r"[._\s]+", "-", component)
    # Remove any other forbidden characters
    component = re.sub(r"[^a-zA-Z0-9-]", "", component)
    # Remove multiple consecutive hyphens
    component = re.sub(r"-+", "-", component)
    # Remove leading/trailing hyphens
    component = component.strip("-")
    return component


def _check_climatology_suffix(ds):
    """
    Check if dataset represents climatology data and should have -clim suffix.

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to check

    Returns
    -------
    str
        "-clim" if climatology, empty string otherwise
    """
    if not has_time_axis(ds):
        return ""
    time_label = get_time_label(ds)
    if time_label and "climatology" in ds[time_label].attrs:
        return "-clim"
    return ""


def create_filepath(ds, rule):
    """
    Generate a filepath when given an xarray dataset and a rule.

    This function generates a filepath for the output file based on
    the given dataset and rule.  The filepath includes the name,
    table_id, institution, source_id, experiment_id, label, grid, and
    optionally the start and end time.

    Parameters
    ----------
    ds : xarray.Dataset
        The input dataset.
    rule : Rule
        The rule object containing information for generating the
        filepath.

    Returns
    -------
    str
        The generated filepath.

    Notes
    -----
    The rule object should have the following attributes:
    cmor_variable, data_request_variable, variant_label, source_id,
    experiment_id, output_directory, and optionally institution.
    """
    name = rule.cmor_variable
    table_id = rule.data_request_variable.table_header.table_id  # Omon
    label = rule.variant_label  # r1i1p1f1
    source_id = rule.source_id  # AWI-CM-1-1-MR
    experiment_id = rule.experiment_id  # historical
    out_dir = rule.output_directory  # where to save output files
    grid = rule.grid_label  # grid_type
    time_range = _filename_time_range(ds, rule)

    # Sanitize components to comply with CMIP6/CMIP7 DRS filename spec
    name = _sanitize_component(name)
    table_id = _sanitize_component(table_id)
    source_id = _sanitize_component(source_id)
    experiment_id = _sanitize_component(experiment_id)
    label = _sanitize_component(label)
    grid = _sanitize_component(grid)

    # Check for climatology suffix
    clim_suffix = _check_climatology_suffix(ds)

    # check if output sub-directory is needed
    enable_output_subdirs = rule._pycmor_cfg.get("enable_output_subdirs", False)
    if enable_output_subdirs:
        subdirs = rule.ga.subdir_path()
        out_dir = f"{out_dir}/{subdirs}"

    frequency_str = rule.data_request_variable.frequency
    compound_str = getattr(rule, "compound_name", "") or ""
    # CMIP7 compound_name has 5 dot-parts; CMIP6 uses 2 (Table.variable).
    is_cmip7 = compound_str.count(".") >= 4

    if is_cmip7:
        # CMIP7 DRS filename:
        # <variable_id>_<branding_suffix>_<frequency>_<region>_<grid_label>_<source_id>_<experiment_id>_<variant_label>[_<time_range>].nc
        parts = compound_str.split(".")
        branding_suffix = _sanitize_component(parts[2])
        # CMIP7 region CV preserves case from the compound: simple codes
        # are lowercase (glb, nh, sh, ...) but latitude-band tokens are
        # uppercase (30S-90S, 30N-90N, ...). The metadata corpus carries
        # the canonical form; lower-casing trips wcrp FILE001 / ATTR004
        # region CV checks because the CV has the uppercase form.
        region = _sanitize_component(parts[4])
        freq_tok = _sanitize_component(frequency_str)
        head = f"{out_dir}/{name}_{branding_suffix}_{freq_tok}_{region}_{grid}_{source_id}_{experiment_id}_{label}"
    else:
        # CMIP6 DRS filename (no institution prefix):
        # <variable_id>_<table_id>_<source_id>_<experiment_id>_<variant_label>_<grid_label>[_<time_range>].nc
        head = f"{out_dir}/{name}_{table_id}_{source_id}_{experiment_id}_{label}_{grid}"

    if frequency_str == "fx" or not time_range:
        filepath = f"{head}{clim_suffix}.nc"
    else:
        filepath = f"{head}_{time_range}{clim_suffix}.nc"

    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    return filepath


def get_offset(rule):
    """convert offset defined on the rule to a timedelta."""
    offset = getattr(rule, "adjust_timestamp", None)
    if offset is not None:
        offset_presets = {
            "first": 0,
            "start": 0,
            "last": 1,
            "end": 1,
            "mid": 0.5,
            "middle": 0.5,
        }
        offset = offset_presets.get(offset, offset)
        try:
            offset = float(offset)
        except (ValueError, TypeError):
            # expect offset to a literal string. Example: "14D"
            offset = pd.Timedelta(offset)
        else:
            # offset is a float value scaled by the approx_interval
            approx_interval = float(rule.data_request_variable.table_header.approx_interval)
            dt = pd.Timedelta(approx_interval, unit="d")
            offset = dt * float(offset)
    return offset


def file_timespan_tail(rule):
    """Grab the last timestamp in each file and return them as a list.
    Also account for offset (if any) defined on the rule"""
    times = []
    try:
        options = {"decode_times": xr.coders.CFDatetimeCoder(use_cftime=True)}
    except AttributeError:
        # in python3.9, xarray does not have coders
        options = {"use_cftime": True}
    for _input in rule.inputs:
        for f in sorted(_input.files):
            ds = xr.open_dataset(str(f), **options)
            time_label = get_time_label(ds)
            if time_label:
                times.append(ds[time_label].values[-1])
    offset = get_offset(rule)
    if offset is not None:
        times = xr.CFTimeIndex(times) + offset
        times = list(times.values)
    return times


def split_data_timespan(ds, rule):
    """
    Splits the dataset into chunks based on the time axis as defined in the source files.

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to split.
    rule : Rule
        The rule object containing information for generating the
        filepath.

    Returns
    -------
    list
        A list of datasets, each containing a chunk of the original dataset.
    """
    time_cuts = file_timespan_tail(rule)
    ncuts = len(time_cuts)
    time_label = get_time_label(ds)
    if not time_label:
        return [ds]
    resampled_times = ds[time_label].values
    ref = pd.DataFrame(resampled_times, columns=["dateindex"])
    ref["mark"] = ncuts
    for ind, timecut in enumerate(reversed(time_cuts), start=1):
        ref.loc[ref.dateindex < timecut, "mark"] = ncuts - ind
    result = []
    for _, grp in ref.groupby("mark"):
        result.append((grp.dateindex.iloc[0], grp.dateindex.iloc[-1]))
    data_chunks = []
    for timespan in result:
        da = ds.sel({time_label: slice(timespan[0], timespan[-1])})
        data_chunks.append(da)
    if not data_chunks:
        data_chunks.append(ds)
    return data_chunks


def _save_dataset_with_native_timespan(
    da,
    rule,
    time_label,
    time_encoding,
    **extra_kwargs,
):
    paths = []
    drv = rule.data_request_variable
    is_fx = getattr(drv, 'frequency', None) in ("fx", "ofx")
    if is_fx:
        # fx / ofx variables are time-invariant. CMIP convention is to write
        # no time coord and no time_bnds at all. The source FESOM/XIOS file
        # ships a singleton time dim (so the model can emit the field once)
        # or, for files like atm_remapped_1m_lsm_<year>.nc, ships repeated
        # monthly copies of the same time-invariant field. In both cases the
        # saved file should carry no time coord, so collapse to the first
        # slice unconditionally rather than only when ``time.size <= 1``.
        # Use ``drop_vars`` instead of ``reset_coords`` to remove the time
        # and time_bnds coords: ``reset_coords`` refuses to drop an indexed
        # dim coord, while ``drop_vars`` removes both the variable and its
        # index in one step.
        if time_label in da.dims:
            da = da.isel({time_label: 0}, drop=True)
        for stale in (time_label, f"{time_label}_bnds", f"{time_label}_bounds"):
            if stale in getattr(da, "coords", {}):
                da = da.drop_vars(stale)
        # The fx dataset no longer has a time dim; xr.save_mfdataset
        # rejects ``unlimited_dims={'time'}`` against a dim that does
        # not exist on the dataset. Strip the kwarg here so the saved
        # file ships with no time-related dim declarations.
        extra_kwargs.pop("unlimited_dims", None)
        datasets = [da]
    else:
        datasets = split_data_timespan(da, rule)

    # Ensure time encoding is properly applied to each dataset
    for i, ds in enumerate(datasets):
        if time_label in ds.variables:
            # If we have custom units and calendar, use xarray's CF encoding function
            # Only apply if both are actual strings (not Mock objects or None)
            if (
                "units" in time_encoding
                and "calendar" in time_encoding
                and isinstance(time_encoding["units"], str)
                and isinstance(time_encoding["calendar"], str)
            ):
                from xarray.coding.times import encode_cf_datetime

                # Get the current time values (should be datetime objects)
                time_values = ds[time_label].values

                # Use xarray's CF encoding function to encode the datetime values
                encoded_values, _, _ = encode_cf_datetime(
                    time_values,
                    units=time_encoding["units"],
                    calendar=time_encoding["calendar"],
                )

                # Replace the time coordinate with the encoded values
                ds[time_label] = xr.DataArray(encoded_values, dims=[time_label], attrs=ds[time_label].attrs.copy())

            # Set time units as an attribute for metadata.
            if "units" in time_encoding and isinstance(time_encoding["units"], str):
                ds[time_label].attrs["units"] = time_encoding["units"]
            # Do NOT set calendar in attrs — xarray's CF encoder copies
            # encoding["calendar"] to the variable's file attributes and
            # raises if the key is already present in attrs. See the
            # corresponding fix in _save_dataset_impl below for details.
            ds[time_label].attrs.pop("calendar", None)

            # Also set the encoding directly on the variable
            ds[time_label].encoding.update(time_encoding)
            # CMIP spec: time:units must match `^days since YYYY-M-D( HH:MM:SS)?$` (no fractional seconds).
            # Derive a clean units string from an explicit reference in this order:
            #   user rule.time_units -> existing encoding/attr (stripped of .fractional) ->
            #   time_origin attr -> first timestamp date.
            _cur = ds[time_label].encoding.get("units") or ds[time_label].attrs.get("units")
            if _cur and "." not in _cur.split(" ")[-1]:
                _units = _cur
            elif _cur:
                _units = _cur.split(".")[0]
            elif ds[time_label].attrs.get("time_origin"):
                _units = f"days since {ds[time_label].attrs['time_origin']}"
            else:
                try:
                    _t0 = pd.Timestamp(str(ds[time_label].values[0]))
                    _units = f"days since {_t0:%Y-%m-%d 00:00:00}"
                except Exception:
                    _units = None
            if _units:
                ds[time_label].attrs.pop("units", None)
                ds[time_label].encoding["units"] = _units
            # Drop stale `bounds` attr if the referenced bounds variable is not present
            _bnd = ds[time_label].attrs.get("bounds")
            if _bnd and _bnd not in ds.variables:
                ds[time_label].attrs.pop("bounds", None)
                ds[time_label].encoding.pop("bounds", None)
            # CF 1.11 §4.4: ESM time axes do not track leap seconds.
            ds[time_label].attrs.setdefault("units_metadata", "leap_seconds: none")
            # Drop stale per-variable `coordinates` encoding (post-rename fixup)
            for _v in ds.data_vars:
                ds[_v].encoding.pop("coordinates", None)
            # cf Appendix A: ``coordinates`` is a data-variable attribute
            # and must not appear as a global. xarray emits one whenever a
            # coord (here time_bnds) is not referenced by any data variable,
            # which the cf-checker reports as an error. Setting it to None
            # on the dataset encoding suppresses that without touching the
            # per-variable attributes. Raised in the DKRZ cli108 review.
            ds.encoding["coordinates"] = None
            # CF 1.12 section 8.4: declare the quantization algorithm.
            ds = _add_cf_quantization_metadata(ds, rule)
            # CF: coordinate variables must not have _FillValue
            for _c in list(ds.coords):
                ds[_c].encoding["_FillValue"] = None

        # CMIP7 cchecker ATTR001: ensure lat/lon bounds exist on regular grids
        datasets[i] = _ensure_lat_lon_bounds_and_external_vars(ds, rule)
        ds = datasets[i]

        # Vector B (cli69): force canonical time encoding regardless of upstream
        # pipeline state. Idempotent — re-running on already-canonical encoding
        # is a no-op. Catches FESOM ocean rules whose chosen file_timespan path
        # bypasses the resample-group code path that recomputes time_bounds.
        if not is_fx and time_label in ds.variables:
            _force_canonical_time_encoding(ds, time_label)

        paths.append(create_filepath(ds, rule))

    # Calculate chunking/compression encoding
    # For dask-backed data, align netCDF chunks with existing dask chunks to avoid
    # expensive rechunking. This makes the write a pure stream: each dask task
    # writes exactly one netCDF chunk with zero read amplification.
    is_dask = any(_is_dask_backed(ds) for ds in datasets)
    if is_dask:
        chunk_encoding = _encoding_from_dask_chunks(datasets[0], rule)
    else:
        chunk_encoding = _calculate_netcdf_chunks(datasets[0], rule)

    # Vector B (cli69): also patch the explicit encoding dict that gets passed
    # to xr.save_mfdataset — it overrides ds[time_label].encoding for the
    # named time variable, so the dataset-level force above is not enough
    # on its own. Safe when there's no time coord (no-op for fx / ofx).
    if not is_fx and time_label in datasets[0].variables:
        enc_dict = chunk_encoding if isinstance(chunk_encoding, dict) else {}
        canonicalize_time_in_encoding_dict(enc_dict, time_label, ds=datasets[0])
        chunk_encoding = enc_dict

    # Default scheduler is "synchronous" to be safe with HDF5 thread-safety;
    # configurable per-rule (netcdf_write_scheduler) for write benchmarks
    # or when using a thread-safe HDF5 build (then "threads" is much faster).
    #
    # In parallel-mode (Prefect+dask-distributed), xr.save_mfdataset(compute=True)
    # would dispatch the array-store dask graph through the global distributed
    # Client, which then tries to pickle the graph for transport to workers.
    # That fails with TypeError("Could not serialize object of type
    # _HLGExprSequence") -> "cannot pickle '_thread.lock' object", because the
    # netCDF4/HDF5 store's writer-lock isn't picklable. Workaround: use
    # compute=False to get a delayed, then compute it explicitly with a
    # synchronous scheduler — that runs in-process and avoids serialization.
    _write_sched = _get_write_scheduler(rule)
    enc = chunk_encoding if chunk_encoding else None
    _save_mfdataset_worker_or_sync(datasets, paths, enc, extra_kwargs,
                                   is_dask, _write_sched)
    return da


def _save_mfdataset_worker_or_sync(datasets, paths, enc, extra_kwargs,
                                   is_dask, scheduler):
    """Multi-file save with the same worker-side compute path as
    ``_safe_to_netcdf`` (Fix #3): compute the lazy datasets on the
    LocalCluster workers via ``Client.compute``, then write the eager
    results via ``xr.save_mfdataset``. Falls back to the legacy
    ``compute=False`` + synchronous-scheduler path when no Client is
    active or the worker path fails."""
    # cf Appendix A: demote bounds coords to plain data variables so xarray
    # does not emit a global ``coordinates`` attribute. See the longer note
    # in ``_safe_to_netcdf``; the same treatment is needed here because the
    # grouped path writes via ``xr.save_mfdataset`` and never reaches that
    # function.
    try:
        _demoted = []
        for _ds in datasets:
            _bnds = [
                c for c in getattr(_ds, "coords", ())
                if str(c).endswith(("_bnds", "_bounds")) or str(c).startswith("bounds_")
            ]
            _d = _ds.reset_coords(_bnds) if _bnds else _ds
            # cf 7.1: bounds variables carry no attributes of their own.
            for _b in _bnds:
                if _b in getattr(_d, "variables", {}):
                    _d[_b].encoding["coordinates"] = None
            _demoted.append(_d)
        datasets = _demoted
    except Exception as _exc:  # pragma: no cover - defensive
        logger.debug(f"could not demote bounds coords before save_mfdataset: {_exc}")

    # Identify the batch for GRAPH_METRIC logging. Use the first dataset's
    # data var name as the rule id, plus the total count of datasets.
    try:
        first_var = next(iter(datasets[0].data_vars), "?") if datasets else "?"
        rule_id = f"{first_var}_mf{len(datasets)}"
    except Exception:
        rule_id = "?_mf"

    if not is_dask:
        logger.info(f"GRAPH_METRIC rule={rule_id} backend=eager nodes=0 layers=0 bytes=0 chunks=0")
        t0 = time.time()
        xr.save_mfdataset(datasets, paths, encoding=enc, **extra_kwargs)
        logger.info(f"GRAPH_RESULT rule={rule_id} backend=eager status=ok elapsed_s={time.time()-t0:.2f}")
        _trim_malloc_arenas()
        return

    # Sum graph metrics across all datasets — what the scheduler will see
    # if we client.compute the list of them.
    sum_keys = sum_layers = sum_bytes = sum_chunks = 0
    for ds in datasets:
        m = _graph_metrics(ds)
        if m is not None:
            k, l, b, c = m
            sum_keys += k or 0
            sum_layers += l or 0
            sum_bytes += b or 0
            sum_chunks += c or 0

    use_worker_compute = os.environ.get("PYCMOR_WORKER_COMPUTE", "auto").lower()
    if use_worker_compute != "off":
        try:
            from dask.distributed import get_client
            client = get_client()
        except (ImportError, ValueError):
            client = None
        if client is not None:
            logger.info(
                f"GRAPH_METRIC rule={rule_id} backend=worker_compute "
                f"nodes={sum_keys} layers={sum_layers} bytes={sum_bytes} chunks={sum_chunks}"
            )
            t0 = time.time()
            try:
                # Compute each lazy dataset on workers; gather eagerly.
                eager_datasets = list(client.compute(datasets, sync=True))
                xr.save_mfdataset(eager_datasets, paths, encoding=enc,
                                  **extra_kwargs)
                logger.info(
                    f"GRAPH_RESULT rule={rule_id} backend=worker_compute "
                    f"status=ok elapsed_s={time.time()-t0:.2f}"
                )
                del eager_datasets
                _trim_malloc_arenas()
                return
            except Exception as exc:
                logger.warning(
                    f"GRAPH_RESULT rule={rule_id} backend=worker_compute "
                    f"status=fallback elapsed_s={time.time()-t0:.2f} exc={type(exc).__name__}"
                )
                logger.warning(
                    f"_save_mfdataset: Client.compute path failed "
                    f"({type(exc).__name__}: {exc}); falling back to "
                    f"synchronous scheduler."
                )

    logger.info(
        f"GRAPH_METRIC rule={rule_id} backend=sync "
        f"nodes={sum_keys} layers={sum_layers} bytes={sum_bytes} chunks={sum_chunks}"
    )
    t0 = time.time()
    delayed = xr.save_mfdataset(
        datasets, paths, encoding=enc, compute=False, **extra_kwargs
    )
    with dask.config.set(scheduler=scheduler):
        delayed.compute()
    logger.info(f"GRAPH_RESULT rule={rule_id} backend=sync status=ok elapsed_s={time.time()-t0:.2f}")
    _trim_malloc_arenas()


def _calculate_netcdf_chunks(ds: xr.Dataset, rule) -> dict:
    """
    Calculate optimal NetCDF chunk sizes based on configuration.

    Parameters
    ----------
    ds : xr.Dataset
        The dataset to calculate chunks for.
    rule : Rule
        The rule object containing configuration.

    Returns
    -------
    dict
        Dictionary mapping variable names to their encoding (including chunks).
    """
    # Check if chunking is enabled
    # First check global config, then allow rule-level override (including from inherit block)
    enable_chunking = rule._pycmor_cfg("netcdf_enable_chunking")
    enable_chunking = getattr(rule, "netcdf_enable_chunking", enable_chunking)
    if not enable_chunking:
        # CF forbids _FillValue on bounds variables; respect explicit None and skip *_bnds.
        _sentinel = object()
        out = {}
        for v in ds.data_vars:
            _pre = ds[v].encoding.get("_FillValue", _sentinel)
            _is_bounds = str(v).endswith(("_bnds", "_bounds"))
            out[v] = {"_FillValue": None if (_pre is None or _is_bounds) else 1.0e20}
        return out

    # Get chunking configuration from global config
    chunk_algorithm = rule._pycmor_cfg("netcdf_chunk_algorithm")
    chunk_size = rule._pycmor_cfg("netcdf_chunk_size")
    chunk_tolerance = rule._pycmor_cfg("netcdf_chunk_tolerance")
    prefer_time = rule._pycmor_cfg("netcdf_chunk_prefer_time")
    compression_level = rule._pycmor_cfg("netcdf_compression_level")
    enable_compression = rule._pycmor_cfg("netcdf_enable_compression")
    compression_codec = "zlib"
    quantize_mode = "BitGroom"
    significant_digits = 5

    # Allow per-rule override of chunking settings (including from inherit block)
    chunk_algorithm = getattr(rule, "netcdf_chunk_algorithm", chunk_algorithm)
    chunk_size = getattr(rule, "netcdf_chunk_size", chunk_size)
    chunk_tolerance = getattr(rule, "netcdf_chunk_tolerance", chunk_tolerance)
    prefer_time = getattr(rule, "netcdf_chunk_prefer_time", prefer_time)
    compression_level = getattr(rule, "netcdf_compression_level", compression_level)
    enable_compression = getattr(rule, "netcdf_enable_compression", enable_compression)
    compression_codec = getattr(rule, "netcdf_compression_codec", compression_codec)
    # Setting ``netcdf_quantize_mode: null`` in the rule/inherit opts out.
    if hasattr(rule, "netcdf_quantize_mode"):
        quantize_mode = rule.netcdf_quantize_mode
    significant_digits = getattr(rule, "netcdf_significant_digits", significant_digits)

    # Calculate chunks based on algorithm
    chunk_functions = {
        "simple": calculate_chunks_simple,
        "even_divisor": calculate_chunks_even_divisor,
        "iterative": calculate_chunks_iterative,
    }
    try:
        chunk_function = chunk_functions[chunk_algorithm]
    except KeyError:
        logger.warning(f"Unknown chunk algorithm: {chunk_algorithm}, using simple")
        chunk_function = calculate_chunks_simple
    try:
        chunks = chunk_function(
            ds,
            target_chunk_size=chunk_size,
            prefer_time_chunking=prefer_time,
        )
        # Generate encoding with chunks and compression
        encoding = get_encoding_with_chunks(
            ds,
            chunks=chunks,
            compression_level=compression_level,
            enable_compression=enable_compression,
            compression_codec=compression_codec,
            quantize_mode=quantize_mode,
            significant_digits=significant_digits,
        )
        logger.info(f"Calculated NetCDF chunks: {chunks}")
        return encoding
    except Exception as e:
        logger.warning(f"Failed to calculate chunks: {e}. Proceeding without chunking.")
        return {}


def save_dataset(da: xr.DataArray, rule):
    """
    Save dataset to one or more files.

    Parameters
    ----------
    da : xr.DataArray
        The dataset to be saved.
    rule : Rule
        The rule object containing information for generating the
        filepath.

    Returns
    -------
    None

    Notes
    -----
    If the dataset does not have a time axis, or if the time axis is a scalar,
    this function will save the dataset to a single file.  Otherwise, it will
    split the dataset into chunks based on the time axis and save each chunk
    to a separate file.

    The filepath will be generated based on the rule object and the time range
    of the dataset.  The filepath will include the name, table_id, institution,
    source_id, experiment_id, label, grid, and optionally the start and end time.

    If the dataset needs resampling (i.e., the time axis does not align with the
    time frequency specified in the rule object), this function will split the
    dataset into chunks based on the time axis and resample each chunk to the
    specified frequency.  The resampled chunks will then be saved to separate
    files.

    NOTE: prior to calling this function, call dask.compute() method,
    otherwise tasks will progress very slow.
    """
    cmor_var = getattr(rule, "cmor_variable", None) or getattr(rule, "name", "?")
    try:
        max_retries = int(os.environ.get("PYCMOR_SAVE_MAX_RETRIES", "2"))
    except (TypeError, ValueError):
        max_retries = 2

    # Watchdog: track growth of the rule's output directory total .nc[+.tmp]
    # bytes. Works for both single-file and multi-file (split-by-timespan)
    # save paths. Resolved at call time so retries see fresh state.
    out_dir = getattr(rule, "output_directory", None)

    def _outdir_size():
        if not out_dir or not os.path.isdir(out_dir):
            return 0
        total = 0
        try:
            for name in os.listdir(out_dir):
                # Count both finalized .nc and in-progress .nc.tmp.
                if name.endswith(".nc") or name.endswith(".nc.tmp") or ".tmp" in name:
                    try:
                        total += os.path.getsize(os.path.join(out_dir, name))
                    except OSError:
                        pass
        except OSError:
            return 0
        return total

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            with _Heartbeat(
                f"save_dataset[{cmor_var}]",
                watch_path=_outdir_size if out_dir else None,
            ):
                return _save_dataset_impl(da, rule)
        except SaveTimeout as exc:
            last_exc = exc
            if attempt < max_retries:
                logger.warning(
                    f"save_dataset[{cmor_var}] timed out "
                    f"(attempt {attempt + 1}/{max_retries + 1}); "
                    f"retrying on a fresh worker. The originally-stuck worker "
                    f"may continue to leak its slot until the SLURM job ends."
                )
            else:
                logger.error(
                    f"save_dataset[{cmor_var}] timed out after "
                    f"{max_retries + 1} attempts; giving up."
                )
                raise
    # Should not reach here; the loop either returns or raises.
    if last_exc is not None:
        raise last_exc


def _save_dataset_impl(da: xr.DataArray, rule):
    time_dtype = rule._pycmor_cfg("xarray_time_dtype")
    time_unlimited = rule._pycmor_cfg("xarray_time_unlimited")
    extra_kwargs = {}
    if time_unlimited:
        extra_kwargs.update({"unlimited_dims": ["time"]})
    time_encoding = {"dtype": time_dtype}
    time_encoding = {k: v for k, v in time_encoding.items() if v is not None}
    # CMIP spec: time:units must match `days since YYYY-M-D( HH:MM:SS)?` (no fractional seconds).
    # Preserve the epoch from upstream data; strip fractional seconds later in the save path.
    # Allow user to define time units and calendar in the rule object
    # Martina has a usecase where she wants to set time units to
    # `days since 1850-01-01` and calendar to `proleptic_gregorian` for
    # historical experiments. See issue #215
    time_units = getattr(rule, "time_units", None)
    time_calendar = getattr(rule, "time_calendar", None)
    # Only add to encoding if they are actual strings (not Mock objects or None)
    if time_units is not None and isinstance(time_units, str):
        time_encoding["units"] = time_units
    if time_calendar is not None and isinstance(time_calendar, str):
        time_encoding["calendar"] = time_calendar
    # Set default calendar if none is specified. CMIP7 recommends
    # ``proleptic_gregorian`` (wcrp_cmip7 TIME003a); CMIP6 historically
    # used ``standard``.
    if time_encoding.get("calendar") is None:
        cmor_ver = getattr(rule, "cmor_version", None)
        time_encoding["calendar"] = (
            "proleptic_gregorian" if cmor_ver == "CMIP7" else "standard"
        )
    if not has_time_axis(da):
        filepath = create_filepath(da, rule)
        # Calculate chunking encoding
        if isinstance(da, xr.DataArray):
            # Ensure DataArray has a name before converting to Dataset
            if da.name is None:
                da = da.rename("data")
            ds_temp = da.to_dataset()
        else:
            ds_temp = da
        ds_temp = _ensure_lat_lon_bounds_and_external_vars(ds_temp, rule)
        chunk_encoding = _calculate_netcdf_chunks(ds_temp, rule)
        return _atomic_to_netcdf(
            ds_temp,
            filepath,
            mode="w",
            format="NETCDF4",
            encoding=chunk_encoding if chunk_encoding else None,
            scheduler=_get_write_scheduler(rule),
            rule=rule,
        )
    time_label = get_time_label(da)
    # Update unlimited_dims to use actual time dimension name (may be time1, time2, etc.)
    if time_unlimited and time_label:
        extra_kwargs["unlimited_dims"] = [time_label]
    if is_scalar(da[time_label]):
        filepath = create_filepath(da, rule)
        # Calculate chunking encoding
        if isinstance(da, xr.DataArray):
            # Ensure DataArray has a name before converting to Dataset
            if da.name is None:
                da = da.rename("data")
            ds_temp = da.to_dataset()
        else:
            ds_temp = da
        ds_temp = _ensure_lat_lon_bounds_and_external_vars(ds_temp, rule)
        chunk_encoding = _calculate_netcdf_chunks(ds_temp, rule)
        # Merge time encoding with chunk encoding
        final_encoding = {time_label: dict(time_encoding)}
        if chunk_encoding:
            final_encoding.update(chunk_encoding)
        # Vector B (cli69): force canonical time encoding even for the scalar
        # time path (a one-point time coord still has calendar / units / dtype
        # that need to round-trip CMIP-clean).
        if time_label in ds_temp.variables:
            _force_canonical_time_encoding(ds_temp, time_label)
            canonicalize_time_in_encoding_dict(
                final_encoding, time_label, ds=ds_temp
            )
        return _atomic_to_netcdf(
            ds_temp,
            filepath,
            mode="w",
            format="NETCDF4",
            encoding=final_encoding,
            scheduler=_get_write_scheduler(rule),
            rule=rule,
            **extra_kwargs,
        )
    if isinstance(da, xr.DataArray):
        # Ensure DataArray has a name before converting to Dataset
        if da.name is None:
            da = da.rename("data")
        da = da.to_dataset()

    # Set time variable attributes
    if rule._pycmor_cfg("xarray_time_set_standard_name"):
        da[time_label].attrs["standard_name"] = "time"
    if rule._pycmor_cfg("xarray_time_set_long_name"):
        da[time_label].attrs["long_name"] = "time"
    if rule._pycmor_cfg("xarray_time_enable_set_axis"):
        time_axis_str = rule._pycmor_cfg("xarray_time_taxis_str")
        da[time_label].attrs["axis"] = time_axis_str
    if rule._pycmor_cfg("xarray_time_remove_fill_value_attr"):
        time_encoding["_FillValue"] = None

    # If we have custom units and calendar, use xarray's CF encoding function
    # Only apply if both are actual strings (not Mock objects or None)
    if (
        "units" in time_encoding
        and "calendar" in time_encoding
        and isinstance(time_encoding["units"], str)
        and isinstance(time_encoding["calendar"], str)
    ):
        from xarray.coding.times import encode_cf_datetime

        # Convert the dataset to Dataset if it's a DataArray
        if isinstance(da, xr.DataArray):
            # Ensure DataArray has a name before converting to Dataset
            if da.name is None:
                da = da.rename("data")
            da = da.to_dataset()

        # Get the current time values (should be datetime objects)
        time_values = da[time_label].values

        # Use xarray's CF encoding function to encode the datetime values
        encoded_values, _, _ = encode_cf_datetime(
            time_values,
            units=time_encoding["units"],
            calendar=time_encoding["calendar"],
        )

        # Replace the time coordinate with the encoded values
        da[time_label] = xr.DataArray(encoded_values, dims=[time_label], attrs=da[time_label].attrs.copy())

    # Set time units as an attribute for metadata. Only set if it is an
    # actual string (not a Mock).
    if "units" in time_encoding and isinstance(time_encoding["units"], str):
        da[time_label].attrs["units"] = time_encoding["units"]
    # Do NOT set calendar in attrs. xarray's CF encoder (encode_cf_variable
    # in xarray/coding/times.py) copies encoding["calendar"] to the file's
    # variable attributes at save time and explicitly refuses if attrs
    # already contains "calendar":
    #   ValueError: Key 'calendar' already exists in attrs on variable
    #     'time', and will not be overwritten.
    # Earlier behaviour set attrs["calendar"] for any non-"standard"
    # calendar (commit ed22f11 era) — this worked accidentally on multi-year
    # cftime data because time_encoding["calendar"] was missing or
    # collapsed to "standard" upstream, but reliably broke for any rule
    # whose loader emitted cftime.DatetimeProlepticGregorian (LPJ-GUESS,
    # FESOM with a calendar override, ...). Strip any stale attrs["calendar"]
    # and let encoding alone carry the calendar through.
    da[time_label].attrs.pop("calendar", None)

    # Ensure the encoding is set on the time variable itself
    if isinstance(da, xr.DataArray):
        # Ensure DataArray has a name before converting to Dataset
        if da.name is None:
            da = da.rename("data")
        da = da.to_dataset()
    da[time_label].encoding.update(time_encoding)
    # CMIP spec: strip fractional seconds from time:units (preserve epoch).
    _cur = da[time_label].encoding.get("units") or da[time_label].attrs.get("units")
    if _cur and "." in _cur.split(" ")[-1]:
        _clean = _cur.split(".")[0]
        da[time_label].attrs.pop("units", None)
        da[time_label].encoding["units"] = _clean
    # Drop stale `bounds` attr if the referenced bounds variable is not present
    bnd = da[time_label].attrs.get("bounds")
    if bnd and bnd not in da.variables:
        da[time_label].attrs.pop("bounds", None)
        da[time_label].encoding.pop("bounds", None)
    # Drop stale per-variable `coordinates` encoding from upstream files; we want
    # the attribute set by std_lib.attributes.set_coordinates (post-rename) to win.
    for v in da.data_vars:
        da[v].encoding.pop("coordinates", None)
    # CF: coordinate variables must not have _FillValue
    for c in list(da.coords):
        da[c].encoding["_FillValue"] = None

    # Vector B (cli69): force canonical time encoding on the dataset before
    # branching to native-timespan or resample-group save paths. Both downstream
    # paths then inherit the override on ds[time_label].encoding (and patch
    # their per-write encoding dicts separately via
    # ``canonicalize_time_in_encoding_dict``). Idempotent.
    if time_label and time_label in da.variables:
        _force_canonical_time_encoding(da, time_label)

    # cli71 fix: ensure time_bnds is present on the dataset before either
    # save path runs. The std_lib.set_time_bounds wrapper builds bnds when
    # the payload is a Dataset, but when the upstream pipeline carried a
    # DataArray (DefaultPipeline after get_variable/timeavg), the wrapper
    # has to drop the bnds aux (xarray refuses a `bnds` dim on a payload
    # DataArray) and the parent coord arrives bare. The resample-group
    # save path re-runs set_time_bounds per group, but the
    # native-timespan path does not — so a FESOM yearly rule that lands
    # on native-timespan (whichever way the non-deterministic
    # file_timespan vs approx_interval comparison falls today) ships a
    # bnds-free file and trips wcrp TIME003.
    if time_label and time_label in da.variables and f"{time_label}_bnds" not in da.variables:
        try:
            from .time_bounds import time_bounds as _re_set_time_bounds
            da = _re_set_time_bounds(da, rule)
        except Exception as _exc:
            logger.warning(
                f"save_dataset: could not re-attach time_bnds: {_exc}"
            )

    if not has_time_axis(da):
        filepath = create_filepath(da, rule)
        # Calculate chunking encoding
        if isinstance(da, xr.DataArray):
            # Ensure DataArray has a name before converting to Dataset
            if da.name is None:
                da = da.rename("data")
            ds_temp = da.to_dataset()
        else:
            ds_temp = da
        ds_temp = _ensure_lat_lon_bounds_and_external_vars(ds_temp, rule)
        da = ds_temp
        chunk_encoding = _calculate_netcdf_chunks(ds_temp, rule)
        _atomic_to_netcdf(
            da,
            filepath,
            mode="w",
            format="NETCDF4",
            encoding=chunk_encoding if chunk_encoding else None,
            scheduler=_get_write_scheduler(rule),
            rule=rule,
            **extra_kwargs,
        )
        return da

    default_file_timespan = rule._pycmor_cfg("file_timespan")
    file_timespan = getattr(rule, "file_timespan", default_file_timespan)
    drv = rule.data_request_variable
    if file_timespan == "file_native" or getattr(drv, 'frequency', None) == "fx" or getattr(getattr(drv, 'table_header', None), 'approx_interval', None) is None:
        return _save_dataset_with_native_timespan(
            da,
            rule,
            time_label,
            time_encoding,
            **extra_kwargs,
        )
    else:
        file_timespan_as_offset = pd.tseries.frequencies.to_offset(file_timespan)
        file_timespan_as_dt = pd.Timestamp.now() + file_timespan_as_offset - pd.Timestamp.now()
        approx_interval = float(rule.data_request_variable.table_header.approx_interval)
        dt = pd.Timedelta(approx_interval, unit="d")
        if file_timespan_as_dt < dt:
            logger.warning(
                f"file_timespan {file_timespan_as_dt} is smaller than approx_interval {dt}"
                "falling back to timespan as defined in the source file"
            )
            return _save_dataset_with_native_timespan(
                da,
                rule,
                time_label,
                time_encoding,
                **extra_kwargs,
            )
        else:
            groups = da.resample({time_label: file_timespan})
            paths = []
            datasets = []
            for group_name, group_ds in groups:
                paths.append(create_filepath(group_ds, rule))
                # The pipeline payload is a DataArray, and xarray refuses to
                # let the bnds aux ride on a DataArray (its 'bnds' dim isn't
                # a subset of (time, nod2)). By the time we reach save_dataset
                # the time_bnds variable that the std_lib wrapper computed has
                # been dropped. Recreate it on each Dataset-shaped group so the
                # canonical bnds make it into the written file. The function
                # is idempotent: if bnds are already present it just realigns
                # time to midpoint(bnds).
                if hasattr(group_ds, "data_vars"):
                    try:
                        from .time_bounds import time_bounds as _set_time_bounds
                        group_ds = _set_time_bounds(group_ds, rule)
                    except Exception as _exc:
                        logger.warning(f"could not re-attach time_bnds in save_dataset: {_exc}")
                # CMIP spec fixups: strip fractional seconds from time:units (preserve epoch);
                # drop stale bounds/coordinates encodings; remove _FillValue from coords.
                if time_label in group_ds.variables:
                    _cur = group_ds[time_label].encoding.get("units") or group_ds[time_label].attrs.get("units")
                    if _cur and "." in _cur.split(" ")[-1]:
                        _clean = _cur.split(".")[0]
                        group_ds[time_label].encoding["units"] = _clean
                        group_ds[time_label].attrs["units"] = _clean
                    _bnd = group_ds[time_label].attrs.get("bounds")
                    if _bnd and _bnd not in group_ds.variables:
                        group_ds[time_label].attrs.pop("bounds", None)
                        group_ds[time_label].encoding.pop("bounds", None)
                    # CF 1.11 §4.4: ESM time axes do not track leap seconds.
                    group_ds[time_label].attrs.setdefault("units_metadata", "leap_seconds: none")
                for _v in group_ds.data_vars:
                    group_ds[_v].encoding.pop("coordinates", None)
                # cf Appendix A: suppress the dataset-level ``coordinates``
                # global that xarray adds for unreferenced coords (see the
                # matching comment in the native-timespan path).
                group_ds.encoding["coordinates"] = None
                # CF 1.12 section 8.4: declare the quantization algorithm.
                group_ds = _add_cf_quantization_metadata(group_ds, rule)
                for _c in list(group_ds.coords):
                    group_ds[_c].encoding["_FillValue"] = None
                # CMIP7 cchecker ATTR001: ensure lat/lon bounds on regular grids
                group_ds = _ensure_lat_lon_bounds_and_external_vars(group_ds, rule)
                # Vector B (cli69): force canonical time encoding on every group
                # dataset before save. Idempotent; covers the case where the
                # upstream pipeline already ran set_time_bounds (no-op) and the
                # case where a custom pipeline skipped it.
                if time_label in group_ds.variables:
                    _force_canonical_time_encoding(group_ds, time_label)
                datasets.append(group_ds)
            # Calculate chunking encoding — align with dask chunks for streaming writes
            is_dask = any(_is_dask_backed(ds) for ds in datasets)
            if is_dask:
                chunk_encoding = _encoding_from_dask_chunks(datasets[0], rule)
            else:
                chunk_encoding = _calculate_netcdf_chunks(datasets[0], rule)
            # Merge time encoding with chunk encoding
            final_encoding = {time_label: dict(time_encoding)}
            if chunk_encoding:
                final_encoding.update(chunk_encoding)
            # CMIP spec: force a clean time:units string (preserve epoch; no fractional seconds).
            _ref = datasets[0][time_label] if time_label in datasets[0].variables else None
            if _ref is not None:
                # xarray normalizes reference datetimes to ISO with `T`, which violates the
                # cchecker regex `days since YYYY-M-D( HH:MM:SS)?`. Use a date-only epoch
                # to stay within the accepted grammar while preserving absolute time.
                # Prefer an epoch that is already canonical: the rule-level
                # ``time_units`` override (issue #215) first, then whatever the
                # coord carries, and only fall back to deriving one from the
                # first timestamp when neither is available. Deriving
                # unconditionally is what produced a different epoch per file
                # (monthly ``days since 1851-01-16``, daily ``1851-01-01``,
                # yearly ``1851-07-02``, decadal ``1855-01-01``) even though
                # every input ships ``seconds since 1850-01-01`` and upstream
                # steps preserve it. A dataset with no single time reference
                # cannot express CMIP7's ``branch_time_in_child``, which is
                # defined as being in "the time units and time model of the
                # child".
                _units = time_encoding.get("units")
                if not _units:
                    _existing = _ref.encoding.get("units") or _ref.attrs.get("units")
                    if isinstance(_existing, str) and _existing.startswith("days since"):
                        _units = _existing
                if not _units:
                    try:
                        _t0 = pd.Timestamp(str(_ref.values[0]))
                        _units = f"days since {_t0:%Y-%m-%d}"
                    except Exception:
                        _units = None
                # Strip fractional seconds / ISO separators so the result stays
                # inside the cchecker grammar ``days since YYYY-M-D( HH:MM:SS)?``.
                if isinstance(_units, str):
                    _units = _units.split(".")[0].replace("T", " ").strip()
                if _units:
                    final_encoding[time_label]["units"] = _units
                    for _ds in datasets:
                        if time_label in _ds.variables:
                            _ds[time_label].attrs.pop("units", None)
                            _ds[time_label].encoding["units"] = _units
            # Vector B (cli69): final_encoding[time] gets passed straight to
            # xr.save_mfdataset and wins over ds[time_label].encoding for any
            # key it carries. Force canonical calendar / units / dtype here so
            # nothing the upstream pipeline did can leak a non-canonical value
            # onto disk (and so future writes that build final_encoding the
            # same way inherit the override for free). Idempotent.
            canonicalize_time_in_encoding_dict(
                final_encoding, time_label, ds=datasets[0]
            )
            # See the parallel-mode HLG-pickling note above the other
            # save_mfdataset call site. Same Fix #3 worker-compute path
            # applied via the shared helper.
            _write_sched = _get_write_scheduler(rule)
            _save_mfdataset_worker_or_sync(datasets, paths, final_encoding,
                                           extra_kwargs, is_dask, _write_sched)
            return da
