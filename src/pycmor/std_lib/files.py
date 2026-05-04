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


def _ensure_lat_lon_bounds_and_external_vars(ds, rule=None):
    """Wrap _ensure_lat_lon_bounds with post-passes that announce external
    cell_measures (CF 1.11 §7.2) and refresh the ``coordinates`` attr."""
    ds = _ensure_lat_lon_bounds_impl(ds, rule)
    ds = _ensure_external_variables(ds)
    ds = _ensure_coordinates_attr(ds)
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


def _rule_get(rule, key, default=None):
    if hasattr(rule, "get"):
        v = rule.get(key)
        if v is not None:
            return v
    return getattr(rule, key, default)


def _native_chunks_per_slab(ds, time_label, slab_size):
    """Estimate native NetCDF source chunks read per slab for the
    largest data variable. Used by `_resolve_slab_size` to skip the
    slab loop when the chunk B-tree traversal cost would dominate
    wall time (1hr-class fields with ~8760 native chunks/file).
    """
    biggest_nbytes = 0
    biggest_var = None
    for v in ds.data_vars:
        nb = int(ds[v].nbytes)
        if nb > biggest_nbytes:
            biggest_nbytes = nb
            biggest_var = v
    if biggest_var is None:
        return 0
    da = ds[biggest_var]
    # Prefer encoding (native NetCDF chunks); fall back to dask chunks.
    chunksizes = da.encoding.get("chunksizes")
    if not chunksizes and da.chunks is not None:
        chunksizes = tuple(max(c) for c in da.chunks)
    if not chunksizes:
        return 0
    n = 1
    for dim, csz in zip(da.dims, chunksizes):
        if not csz:
            continue
        if dim == time_label:
            # along the slabbing axis: slab_size / chunk_along_time
            n *= max(1, (slab_size + csz - 1) // csz)
        else:
            n *= max(1, (ds.sizes.get(dim, csz) + csz - 1) // csz)
    return n


def _resolve_slab_size(ds, rule):
    """Decide a per-output slab_size (along the time axis) for streaming
    write. Returns None when slab-loop should be skipped (small dataset
    or rule opts out).

    Resolution order:
      1. ``rule.slab_size`` — explicit override (int). ``0``/``False`` opts out.
      2. ``rule.slab_target_bytes`` — target raw bytes per slab; default 1 GB.
         slab_size = floor(target / bytes_per_step), clamped to [1, n_steps].
      3. Skip slab loop if ds.nbytes <= 2 × target (small enough to fit
         without slabbing).
      4. Chunk-count guard: skip slab loop if estimated native chunks per
         slab > ``rule.slab_max_native_chunks`` (default 600). Per-slab
         B-tree traversal of >>600 native chunks dominates wall time on
         1hr-class fields (8760 chunks total) — verified by bench v15/v16.

    Slab-loop is also skipped when the dataset has no time axis or only
    one timestep.
    """
    explicit = _rule_get(rule, "slab_size")
    if explicit is False or (isinstance(explicit, int) and explicit <= 0):
        return None
    time_label = get_time_label(ds) if isinstance(ds, xr.Dataset) else None
    if not time_label or ds.sizes.get(time_label, 1) <= 1:
        return None
    n_steps = int(ds.sizes[time_label])
    if explicit:
        try:
            slab = max(1, min(int(explicit), n_steps))
        except (TypeError, ValueError):
            return None
    else:
        target = int(_rule_get(rule, "slab_target_bytes", 1_000_000_000) or 0)
        if target <= 0:
            return None
        if int(ds.nbytes) <= 2 * target:
            return None
        bytes_per_step = max(1, int(ds.nbytes) // n_steps)
        slab = min(max(1, target // bytes_per_step), n_steps)
    # Chunk-count guard: skip slab loop for high-chunk-count inputs.
    max_chunks = int(_rule_get(rule, "slab_max_native_chunks", 600) or 0)
    if max_chunks > 0:
        n_chunks = _native_chunks_per_slab(ds, time_label, slab)
        if n_chunks > max_chunks:
            logger.info(
                f"slab loop skipped: {n_chunks} native source chunks/slab "
                f"exceeds slab_max_native_chunks={max_chunks} (1hr-class field?)"
            )
            return None
    return slab


def _input_paths_from_rule(rule):
    """Best-effort enumeration of input file paths for a rule. Used to
    fadvise(DONTNEED) at end-of-loop so the next rule's run starts with
    a clean page cache."""
    paths = []
    for collection in getattr(rule, "inputs", []) or []:
        for f in getattr(collection, "files", []) or []:
            paths.append(str(f))
    return paths


def _fadvise_dontneed(path):
    import os as _os
    try:
        fd = _os.open(str(path), _os.O_RDONLY)
        try:
            _os.posix_fadvise(fd, 0, 0, _os.POSIX_FADV_DONTNEED)
        finally:
            _os.close(fd)
    except Exception as exc:
        logger.debug(f"  → fadvise(DONTNEED) failed for {path}: {exc}")


def _save_one_with_slab_loop(ds, path, encoding, extra_kwargs, rule, slab_size):
    """Append-along-unlimited-time write of `ds` in slabs of `slab_size`
    timesteps each. Encoding (chunksizes / compression / quantize) is
    applied on the first slab; subsequent slabs append.

    On the first slab, every dimension whose size matches the time axis
    length is marked unlimited. CMIP datasets often carry auxiliary time
    dimensions (``time1``, ``time2`` for sub-time statistics) at the same
    size as ``time``; if any of those is left as a fixed dim on slab 0,
    appending slab 1 fails with
    ``ValueError("Unable to update size for existing dimension 'time1' (n != m)")``.

    After each slab and at end of loop, calls posix_fadvise(POSIX_FADV_DONTNEED)
    on the output file (and on the rule's input files at end-of-loop) so
    the kernel reclaims page cache instead of letting it grow to the full
    file size during the rule and persist into the next rule.
    """
    import gc

    time_label = get_time_label(ds)
    if not time_label or ds.sizes.get(time_label, 1) <= 1 or slab_size <= 0:
        # No-op safety net: just write once.
        ds.to_netcdf(path, mode="w", format="NETCDF4", encoding=encoding if encoding else None, **extra_kwargs)
        return
    n = int(ds.sizes[time_label])
    n_slabs = (n + slab_size - 1) // slab_size
    # Auxiliary time-like dims (time1, time2, ...) that share the time-axis
    # length and would otherwise be written fixed-size on slab 0, breaking
    # subsequent appends.
    unlimited_dims = [d for d, s in ds.sizes.items() if int(s) == n]
    logger.info(
        f"slab-loop save: {n} timesteps along '{time_label}', "
        f"slab_size={slab_size} → {n_slabs} slabs → {path} "
        f"(unlimited dims: {unlimited_dims})"
    )
    if Path(path).exists():
        Path(path).unlink()
    for i in range(n_slabs):
        s, e = i * slab_size, min((i + 1) * slab_size, n)
        slab = ds.isel({time_label: slice(s, e)})
        if i == 0:
            kwargs = dict(extra_kwargs)
            kwargs["unlimited_dims"] = unlimited_dims
            slab.to_netcdf(path, mode="w", format="NETCDF4", encoding=encoding if encoding else None, **kwargs)
        else:
            slab.to_netcdf(path, mode="a")
        _fadvise_dontneed(path)
        del slab
        gc.collect()
    # Tell the kernel we're done with the input files for this rule, so
    # the next rule starts with reclaimable pages instead of inheriting
    # this rule's input cache. Per-slab fadvise on inputs is wasted work
    # (dask reads chunks lazily), but one pass at end of loop is cheap
    # and meaningfully reduces cumulative cgroup pressure across rules.
    for src in _input_paths_from_rule(rule):
        _fadvise_dontneed(src)


def _save_loop_or_mf(datasets, paths, encoding, extra_kwargs, rule):
    """Save list of (dataset, path) pairs.

    When ``rule.slab_size`` is set (or auto-derived from
    ``rule.slab_target_bytes``, default 1 GB), each dataset is written
    via a slab-loop with explicit free + posix_fadvise(DONTNEED) between
    slabs. Caps cgroup peak at ~slab-size of input page cache + ~1 GB
    output buffer, which lets more rules run concurrently per worker
    node — see bench_hr_ua_6hr_results.md for the data behind this.

    When ``rule.save_per_file`` is truthy (legacy bench knob), loops
    `to_netcdf` per dataset (one full dataset per file, no slab split)
    and drops references between iterations.

    When ``rule.save_engine`` is set, threads it through as the xarray
    backend engine (e.g. ``h5netcdf``).

    Default (none of the above): a single ``xr.save_mfdataset`` call,
    matching pre-slab behaviour for small datasets.
    """
    save_per_file = bool(_rule_get(rule, "save_per_file", False))
    engine = _rule_get(rule, "save_engine")
    base_kwargs = dict(extra_kwargs)
    if engine:
        base_kwargs["engine"] = engine
    enc = encoding if encoding else None
    # Decide whether to engage the slab loop on a per-dataset basis. Each
    # dataset in the list is its own output file, so slab decisions are
    # independent (one rule may produce both a small fx file and a heavy
    # time-resolved file via different paths through this helper).
    use_slab = []
    for d in datasets:
        slab_size = _resolve_slab_size(d, rule)
        use_slab.append(slab_size)

    if any(s is not None for s in use_slab):
        for i, (d, p, slab_size) in enumerate(zip(datasets, paths, use_slab)):
            if slab_size is not None:
                _save_one_with_slab_loop(d, p, enc, base_kwargs, rule, slab_size)
            else:
                d.to_netcdf(p, mode="w", format="NETCDF4", encoding=enc, **base_kwargs)
            datasets[i] = None
        return

    if save_per_file:
        for i, (ds, p) in enumerate(zip(datasets, paths)):
            ds.to_netcdf(p, mode="w", format="NETCDF4", encoding=enc, **base_kwargs)
            datasets[i] = None
        return
    xr.save_mfdataset(datasets, paths, encoding=enc, **base_kwargs)


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
    _write_sched = _get_write_scheduler(rule)
    if is_dask:
        with dask.config.set(scheduler=_write_sched):
            _save_loop_or_mf(datasets, paths, chunk_encoding, extra_kwargs, rule)
    else:
        _save_loop_or_mf(datasets, paths, chunk_encoding, extra_kwargs, rule)
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
        return ds_temp.to_netcdf(
            filepath,
            mode="w",
            format="NETCDF4",
            encoding=chunk_encoding if chunk_encoding else None,
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
        return ds_temp.to_netcdf(
            filepath,
            mode="w",
            format="NETCDF4",
            encoding=final_encoding,
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
        da.to_netcdf(
            filepath,
            mode="w",
            format="NETCDF4",
            encoding=chunk_encoding if chunk_encoding else None,
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
            if is_dask:
                _write_sched = _get_write_scheduler(rule)
                with dask.config.set(scheduler=_write_sched):
                    _save_loop_or_mf(datasets, paths, final_encoding, extra_kwargs, rule)
            else:
                _save_loop_or_mf(datasets, paths, final_encoding, extra_kwargs, rule)
            return da
