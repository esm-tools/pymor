"""Pipeline steps for CF cell-measure (fx) variables.

CMIP7 variables that reference ``cell_measures`` (e.g. ``area: areacello``)
need the measure itself shipped as a companion fx-frequency file.
These steps load the measure from the model's grid/mesh and make it
available to pycmor's standard save path.

The three steps (``load_gridfile``, ``compute_areacello``,
``compute_areacella``) together with the :class:`AreacelloFxPipeline`
and :class:`AreacellaFxPipeline` frozen pipelines in
``pycmor.core.pipeline`` cover the common cases. They are generic over
model; any config with ``grid_file`` pointing at a mesh containing
``cell_area`` (ocean) or with loadable lat/lon coords (atmosphere)
can reuse them.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from ..core.logging import logger


def load_gridfile(data, rule):
    """Load ``rule.grid_file`` as an xarray Dataset.

    Drop-in replacement for ``pycmor.core.gather_inputs.load_mfdataset``
    at the head of an fx pipeline: instead of reading time-series model
    output, it reads the time-invariant grid/mesh file.

    Works for any model that stores grid info in a NetCDF file
    (FESOM ``mesh.nc``, ICON grid file, atmospheric grid descriptor).
    """
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for load_gridfile step")
    logger.info(f"Loading grid file: {grid_file}")
    return xr.open_dataset(grid_file)


def compute_areacello(data, rule):
    """Ocean grid-cell area as read from an unstructured mesh.

    Reads ``cell_area`` (or ``cluster_area`` as a fallback) from the
    mesh Dataset produced by :func:`load_gridfile`. No computation —
    the mesh already stores the per-node surface area in m².
    """
    for name in ("cell_area", "cluster_area"):
        if name in data:
            area = data[name]
            break
    else:
        raise ValueError("Mesh must contain 'cell_area' or 'cluster_area' for areacello")

    result = area.copy()
    result.attrs = {
        "units": "m2",
        "standard_name": "cell_area",
        "long_name": "Ocean Grid-Cell Area",
        "cell_methods": "area: sum",
    }
    result.name = rule.model_variable
    return result


def compute_areacella(data, rule):
    """Atmospheric grid-cell area from lat/lon on a regular grid.

    Uses the spherical-Earth formula
    ``area = R² · Δλ · |sin(φ+Δφ/2) − sin(φ−Δφ/2)|`` (Earth radius
    R = 6 371 000 m). ``data`` is any field on the target grid; only
    its lat/lon coords are used.
    """
    R = 6371000.0

    lat = None
    lon = None
    for coord_name in data.coords:
        if "lat" in coord_name.lower():
            lat = data.coords[coord_name]
        if "lon" in coord_name.lower():
            lon = data.coords[coord_name]
    if lat is None or lon is None:
        raise ValueError("Cannot find lat/lon coordinates in input data")

    lat_vals = np.deg2rad(lat.values)
    lon_vals = np.deg2rad(lon.values)

    dlat = float(np.abs(np.diff(lat_vals).mean()))
    dlon = float(np.abs(np.diff(lon_vals).mean()))

    lat_upper = lat_vals + dlat / 2
    lat_lower = lat_vals - dlat / 2
    area_1d = R**2 * dlon * np.abs(np.sin(lat_upper) - np.sin(lat_lower))
    area_2d = np.broadcast_to(area_1d[:, np.newaxis], (len(lat_vals), len(lon_vals)))

    result = xr.DataArray(
        area_2d,
        dims=[lat.dims[0], lon.dims[0]],
        coords={lat.name: lat, lon.name: lon},
    )
    result.attrs = {
        "units": "m2",
        "standard_name": "cell_area",
        "long_name": "Grid-Cell Area for Atmospheric Grid Variables",
        "cell_methods": "area: sum",
    }
    result.name = rule.model_variable
    return result
