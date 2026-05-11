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
import threading
import time
from pathlib import Path

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
                        logger.error(
                            f"  ✗ {self.label}: no I/O progress for "
                            f"{self.timeout_s / 60:.0f} min on "
                            f"{self.watch_path!r}; flagging SaveTimeout. "
                            f"Worker may be stuck in a Lustre write syscall "
                            f"and leak its slot until SLURM kills the job — "
                            f"retry will run on a different worker."
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
            status = "ok" if exc_type is None else f"failed ({exc_type.__name__})"
            logger.info(f"  ✓ {self.label} done in {elapsed:.0f}s [{status}]")
        # If watchdog flagged a timeout AND the wrapped block didn't already
        # raise something else, propagate as SaveTimeout to the retry loop.
        if self._timed_out and exc_type is None:
            raise SaveTimeout(self.label)
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
    otherwise propagate from the load engine into the save call.

    Specifically: when the input was opened with ``engine="h5netcdf"``,
    coord variables (``lat``, ``lon``, ``time*``, etc.) get an
    ``encoding`` with ``compression="unknown"`` because h5netcdf doesn't
    recognise the BLOSC HDF5 filter (filter id 32001). The default
    netcdf4 backend instead reports ``blosc={...}``. xarray's
    ``to_netcdf`` then fails on save with
    ``ValueError("Unsupported value for compression kwarg ...")``.

    Data variables are unaffected because pycmor builds their encoding
    from scratch in ``_encoding_from_dask_chunks``. We only need to
    sanitise coords + non-data variables.
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
    return ds


def _ensure_lat_lon_bounds_and_external_vars(ds, rule=None):
    """Wrap _ensure_lat_lon_bounds with post-passes that announce external
    cell_measures (CF 1.11 §7.2) and refresh the ``coordinates`` attr."""
    ds = _ensure_lat_lon_bounds_impl(ds, rule)
    ds = _ensure_external_variables(ds)
    ds = _ensure_coordinates_attr(ds)
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
            dim_name = coord.dims[0]
            vdim = mb.dims[1]
            data = mb.values
            ds[bname] = xr.DataArray(
                data,
                dims=(dim_name, vdim),
                attrs={},
            )
            ds[bname].encoding["_FillValue"] = None
            ds[name].attrs["bounds"] = bname
    finally:
        mesh.close()
    return ds


def _is_dask_backed(ds):
    """Check if any variable in a dataset/dataarray is backed by dask arrays."""
    if isinstance(ds, xr.DataArray):
        return ds.chunks is not None
    return any(v.chunks is not None for v in ds.data_vars.values())


def _safe_to_netcdf(ds_or_da, *args, scheduler="synchronous", **kwargs):
    """Wrapper around ``to_netcdf`` that works around the
    ``TypeError: Could not serialize object of type _HLGExprSequence``
    failure (root cause: ``cannot pickle '_thread.lock' object``) seen
    when a Prefect+DaskTaskRunner-backed distributed.Client is active
    and xarray dispatches the array-store dask graph through it.

    When the input is dask-backed: call ``to_netcdf(compute=False)`` to
    get a Delayed without dispatching to the Client, then ``compute()``
    it under ``dask.config.set(scheduler=...)`` so the graph runs
    in-process (no inter-worker pickling).

    When the input is eager (numpy-backed): just call ``to_netcdf``.
    No dask graph is built, no serialization happens.

    Alternative considered: ``lock=False`` at open time (xarray docs;
    pydata/xarray#3961, #8442) avoids putting the lock in the graph
    in the first place. We did not adopt that here because
    (a) it requires a thread-safe HDF5 build (we have one on Levante),
    (b) it shifts thread-safety responsibility to the caller, and
    (c) the present approach works without changing input-loading code.
    Worth revisiting in a future round if save-side perf becomes a
    bottleneck.

    See: dask/distributed#780, pydata/xarray#4406, dask/dask#10238.
    """
    if _is_dask_backed(ds_or_da):
        delayed = ds_or_da.to_netcdf(*args, compute=False, **kwargs)
        with dask.config.set(scheduler=scheduler):
            delayed.compute()
        return None
    return ds_or_da.to_netcdf(*args, **kwargs)


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
            var_encoding["chunksizes"] = tuple(max(c) for c in da.chunks)
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
    start = pd.Timestamp(str(ds[time_label].data[0]))
    end = pd.Timestamp(str(ds[time_label].data[-1]))
    # frequency_str = rule.get("frequency_str")
    frequency_str = rule.data_request_variable.frequency
    if frequency_str in ("yr", "yrPt", "dec"):
        # For yearly data, the end year should be the year of the last timestamp
        # not the year after it (fix off-by-one error)
        return f"{start:%Y}-{end:%Y}"
    if frequency_str in ("mon", "monC", "monPt"):
        return f"{start:%Y%m}-{end:%Y%m}"
    if frequency_str == "day":
        return f"{start:%Y%m%d}-{end:%Y%m%d}"
    if frequency_str in ("6hr", "3hr", "1hr", "6hrPt", "3hrPt", "1hrPt", "1hrCM"):
        _start = start.round("1min")
        _end = end.round("1min")
        return f"{_start:%Y%m%d%H%M}-{_end:%Y%m%d%H%M}"
    if frequency_str == "subhrPt":
        _start = start.round("1s")
        _end = end.round("1s")
        return f"{_start:%Y%m%d%H%M%S}-{_end:%Y%m%d%H%M%S}"
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
        # CMIP7 region CV is lowercase (glb, nh, sh, ...); match the global attribute.
        region = _sanitize_component(parts[4]).lower()
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
    if getattr(drv, 'frequency', None) == "fx":
        # fx variables: write a single file, no time splitting
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

            # Set time units and calendar as attributes for consistency
            # Only set if they are actual strings (not Mock objects)
            # But avoid setting calendar attribute if it conflicts with encoding
            if "units" in time_encoding and isinstance(time_encoding["units"], str):
                ds[time_label].attrs["units"] = time_encoding["units"]
            # Only set calendar attribute if we have custom calendar (not default "standard")
            if (
                "calendar" in time_encoding
                and isinstance(time_encoding["calendar"], str)
                and time_encoding["calendar"] != "standard"
            ):
                ds[time_label].attrs["calendar"] = time_encoding["calendar"]

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
            # CF: coordinate variables must not have _FillValue
            for _c in list(ds.coords):
                ds[_c].encoding["_FillValue"] = None

        # CMIP7 cchecker ATTR001: ensure lat/lon bounds exist on regular grids
        datasets[i] = _ensure_lat_lon_bounds_and_external_vars(ds, rule)
        ds = datasets[i]

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
    if is_dask:
        delayed = xr.save_mfdataset(
            datasets, paths, encoding=enc, compute=False, **extra_kwargs
        )
        with dask.config.set(scheduler=_write_sched):
            delayed.compute()
    else:
        xr.save_mfdataset(
            datasets, paths, encoding=enc, **extra_kwargs
        )
    return da


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
    # Set default calendar if none is specified
    if time_encoding.get("calendar") is None:
        time_encoding["calendar"] = "standard"
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
        final_encoding = {time_label: time_encoding}
        if chunk_encoding:
            final_encoding.update(chunk_encoding)
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

    # Set time units and calendar as attributes (for metadata)
    # Only set if they are actual strings (not Mock objects)
    # But avoid setting calendar attribute if it conflicts with encoding
    if "units" in time_encoding and isinstance(time_encoding["units"], str):
        da[time_label].attrs["units"] = time_encoding["units"]
    # Only set calendar attribute if we have custom calendar (not default "standard")
    if (
        "calendar" in time_encoding
        and isinstance(time_encoding["calendar"], str)
        and time_encoding["calendar"] != "standard"
    ):
        da[time_label].attrs["calendar"] = time_encoding["calendar"]

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
                for _c in list(group_ds.coords):
                    group_ds[_c].encoding["_FillValue"] = None
                # CMIP7 cchecker ATTR001: ensure lat/lon bounds on regular grids
                group_ds = _ensure_lat_lon_bounds_and_external_vars(group_ds, rule)
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
                try:
                    _t0 = pd.Timestamp(str(_ref.values[0]))
                    _units = f"days since {_t0:%Y-%m-%d}"
                except Exception:
                    _units = None
                if _units:
                    final_encoding[time_label]["units"] = _units
                    for _ds in datasets:
                        if time_label in _ds.variables:
                            _ds[time_label].attrs.pop("units", None)
                            _ds[time_label].encoding["units"] = _units
            # See the parallel-mode HLG-pickling note above the other
            # save_mfdataset call site. Same workaround applies here.
            if is_dask:
                _write_sched = _get_write_scheduler(rule)
                delayed = xr.save_mfdataset(
                    datasets, paths, encoding=final_encoding,
                    compute=False, **extra_kwargs
                )
                with dask.config.set(scheduler=_write_sched):
                    delayed.compute()
            else:
                xr.save_mfdataset(
                    datasets, paths, encoding=final_encoding,
                    **extra_kwargs,
                )
            return da
