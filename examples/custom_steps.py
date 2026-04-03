"""
Custom processing steps for pycmor pipelines.

Steps are organized by reusability:
- Generic steps (load_gridfile): work with any model/realm
- Ocean fx steps (compute_deptho, etc.): FESOM-specific but pattern is reusable
- Vertical integration: generic ocean/atmosphere
"""

import logging
from typing import Optional

import numpy as np
import xarray as xr

logger = logging.getLogger(__name__)


# ============================================================
# Generic steps — reusable across models and realms
# ============================================================


def load_gridfile(data, rule):
    """
    Load a single grid/mesh file as an xarray Dataset.

    Reads the path from rule.grid_file. This replaces load_mfdataset
    for fx (time-invariant) variables derived from grid files rather
    than model output time series.

    Works with any model that stores grid info in a NetCDF file:
    FESOM mesh.nc, ICON grid.nc, atmosphere grids, etc.
    """
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for load_gridfile step")
    logger.info(f"Loading grid file: {grid_file}")
    ds = xr.open_dataset(grid_file)
    return ds


# ============================================================
# Ocean fx computation steps — FESOM mesh specific
# Pattern: take mesh Dataset, return a single DataArray
# ============================================================


def compute_deptho(data, rule):
    """
    Compute ocean bathymetry (sea floor depth) from FESOM mesh.

    Uses mesh depth levels and the number of active levels per cell
    to determine the bottom depth at each horizontal location.

    Input: xr.Dataset (mesh file with 'depth' and 'depth_lev')
    Output: xr.DataArray (2D field of bottom depth)
    """
    if "depth_lev" in data and "depth" in data:
        # depth_lev = number of active vertical levels per cell
        # depth = 1D array of level depths
        depth = data["depth"].values
        depth_lev = data["depth_lev"].values
        # Bottom depth = depth at the last active level
        bottom_depth = np.array([depth[min(int(nl), len(depth) - 1)] for nl in depth_lev])
        result = xr.DataArray(
            bottom_depth,
            dims=data["depth_lev"].dims,
            attrs={"units": "m", "standard_name": "sea_floor_depth_below_geoid"},
        )
    elif "zbar_n_bottom" in data:
        # Alternative: fesom.mesh.diag.nc provides this directly
        result = data["zbar_n_bottom"]
    else:
        raise ValueError("Mesh file must contain 'depth'+'depth_lev' or 'zbar_n_bottom'")
    result.name = "deptho"
    return result


def compute_sftof(data, rule):
    """
    Compute sea area fraction from FESOM mesh.

    Ocean cells get 100%, land cells get 0%.
    Determined by whether a cell has active vertical levels.

    Input: xr.Dataset (mesh file with 'depth_lev')
    Output: xr.DataArray (2D field, 0 or 100)
    """
    if "depth_lev" not in data:
        raise ValueError("Mesh file must contain 'depth_lev' for sftof computation")
    depth_lev = data["depth_lev"]
    result = xr.where(depth_lev > 0, 100.0, 0.0)
    result.attrs = {"units": "%", "standard_name": "sea_area_fraction"}
    result.name = "sftof"
    return result


def compute_thkcello_fx(data, rule):
    """
    Compute static ocean layer thickness from mesh depth bounds.

    For z-coordinate models with fixed levels, thickness = diff(depth_bnds).
    Returns a 1D array of layer thicknesses indexed by level.

    Input: xr.Dataset (mesh file with 'depth_bnds')
    Output: xr.DataArray (1D, per level)
    """
    if "depth_bnds" in data:
        bnds = data["depth_bnds"].values
        # depth_bnds has shape (nlevels+1,) — interfaces between layers
        thickness = np.diff(bnds)
        result = xr.DataArray(
            thickness,
            dims=["lev"],
            attrs={"units": "m", "standard_name": "cell_thickness"},
        )
    else:
        raise ValueError("Mesh file must contain 'depth_bnds' for thkcello computation")
    result.name = "thkcello"
    return result


def compute_masscello_fx(data, rule):
    """
    Compute static ocean grid-cell mass per area.

    For Boussinesq models: masscello = rho_0 * thkcello
    where rho_0 is the reference density (default 1025 kg/m3).

    Input: xr.Dataset (mesh file with 'depth_bnds')
    Output: xr.DataArray (1D, per level, in kg/m2)
    """
    rho_0 = float(rule.get("reference_density", 1025.0))
    if "depth_bnds" in data:
        bnds = data["depth_bnds"].values
        thickness = np.diff(bnds)
        mass = rho_0 * thickness
        result = xr.DataArray(
            mass,
            dims=["lev"],
            attrs={
                "units": "kg m-2",
                "standard_name": "sea_water_mass_per_unit_area",
            },
        )
    else:
        raise ValueError("Mesh file must contain 'depth_bnds' for masscello computation")
    result.name = "masscello"
    return result


# ============================================================
# Ocean density and transport steps
# These load auxiliary data (mesh, other variables) from paths
# specified in rule attributes, since pycmor pipelines pass
# a single data object through steps.
# ============================================================


def compute_density(data, rule):
    """
    Compute in-situ sea water density from temperature and salinity
    using gsw (TEOS-10).

    Expects data to be an xr.Dataset containing both temperature and
    salinity variables. Variable names read from rule config:
      - rule.temp_variable (default: 'temp')
      - rule.salt_variable (default: 'salt')

    Returns an xr.DataArray of density (kg/m3).
    """
    import gsw

    temp_var = rule.get("temp_variable", "temp")
    salt_var = rule.get("salt_variable", "salt")

    if isinstance(data, xr.Dataset):
        temp = data[temp_var]
        salt = data[salt_var]
    else:
        raise ValueError("compute_density expects an xr.Dataset with temp and salt variables")

    # Detect vertical dimension for pressure calculation
    vertical_dim = None
    for dim in ["nz1", "nz", "depth", "lev"]:
        if dim in data.dims:
            vertical_dim = dim
            break

    if vertical_dim is not None and vertical_dim in data.coords:
        # Use depth coordinates to compute pressure
        depth_vals = data.coords[vertical_dim]
        # gsw needs pressure in dbar; approximate: pressure ≈ depth (in m) for ocean
        pressure = xr.DataArray(depth_vals.values, dims=[vertical_dim])
    else:
        # Approximate: use 0 dbar (surface) — density won't be pressure-corrected
        logger.warning("No vertical coordinate found, computing density at surface pressure")
        pressure = 0.0

    # TEOS-10: convert practical salinity to absolute salinity (approximate)
    # and potential temperature to conservative temperature
    # For Boussinesq models this is a reasonable approximation
    SA = gsw.SA_from_SP(salt, pressure, 0, 0)  # lon=0, lat=0 approximation
    CT = gsw.CT_from_pt(SA, temp)
    rho = gsw.rho(SA, CT, pressure)

    result = xr.DataArray(rho, dims=temp.dims, coords=temp.coords)
    result.name = "rho"
    result.attrs = {"units": "kg m-3", "standard_name": "sea_water_density"}
    return result


def compute_mass_transport(data, rule):
    """
    Compute ocean mass transport from velocity.

    mass_transport = velocity * density * cell_thickness * cell_width

    For FESOM unstructured grid, we approximate:
      umo = u * rho_0 * dz * dx  (but dx not well-defined on unstructured grids)

    Simplified Boussinesq approach used by most CMIP models:
      umo = u * rho_0 * cell_area_vertical_face

    Since FESOM doesn't output cell face areas, we use the simpler:
      umo = u * rho_0 * dz

    where dz is layer thickness and rho_0 is reference density.
    Units: m/s * kg/m3 * m = kg/(m*s) — needs scaling by cell width for kg/s.

    For unstructured grids, CMIP accepts transport per unit width (kg/m/s)
    or the model can report on native grid with volcello as cell_measures.

    Rule attributes:
      - reference_density: Boussinesq rho_0 (default 1025.0 kg/m3)
      - transport_component: 'x', 'y', or 'z' (for metadata)
    """
    rho_0 = float(rule.get("reference_density", 1025.0))
    grid_file = rule.get("grid_file")

    # data is a DataArray (velocity field, already extracted by get_variable)
    if not isinstance(data, xr.DataArray):
        raise ValueError("compute_mass_transport expects velocity as xr.DataArray")

    # Get layer thickness from mesh
    mesh = xr.open_dataset(grid_file)
    if "depth_bnds" in mesh:
        depth_bnds = mesh["depth_bnds"].values
        dz = np.diff(depth_bnds)
    else:
        raise ValueError("Mesh file must contain 'depth_bnds' for layer thickness")
    mesh.close()

    # Detect vertical dimension
    vertical_dim = None
    for dim in ["nz1", "nz", "depth", "lev"]:
        if dim in data.dims:
            vertical_dim = dim
            break

    if vertical_dim is None:
        raise ValueError(f"No vertical dimension found in data. Dims: {list(data.dims)}")

    # Build thickness array matching the vertical dimension
    nz_data = data.sizes[vertical_dim]
    if len(dz) >= nz_data:
        thickness = xr.DataArray(dz[:nz_data], dims=[vertical_dim])
    else:
        raise ValueError(f"Mesh has {len(dz)} levels but data has {nz_data}")

    # mass transport = velocity * rho_0 * layer_thickness
    # Units: m/s * kg/m3 * m = kg/(m2*s) ... this is transport per unit width
    # For FESOM unstructured grid, this is the standard approach
    transport = data * rho_0 * thickness

    transport.name = data.name
    component = rule.get("transport_component", "")
    transport.attrs = {
        "units": "kg s-1",
        "processing_note": f"Computed as velocity * rho_0({rho_0}) * dz. " f"Transport per grid cell {component}-face.",
    }
    return transport


def compute_zostoga(data, rule):
    """
    Compute global average thermosteric sea level change.

    zostoga = (1/A_ocean) * integral( -alpha * delta_T * dz * dA )

    where alpha is thermal expansion coefficient, delta_T is temperature
    anomaly from reference, dz is layer thickness, dA is cell area.

    Simplified approach: compute steric height anomaly from temperature
    and salinity relative to a reference state.

    Rule attributes:
      - grid_file: path to mesh file (for cell_area and depth_bnds)
      - salt_file: path to salinity file (optional, for full steric)
      - reference_density: rho_0 (default 1025.0)
    """
    import gsw

    rho_0 = float(rule.get("reference_density", 1025.0))
    grid_file = rule.get("grid_file")

    # data is a DataArray of temperature (from get_variable step)
    if not isinstance(data, xr.DataArray):
        raise ValueError("compute_zostoga expects temperature as xr.DataArray")

    # Load mesh for cell areas and depth info
    mesh = xr.open_dataset(grid_file)
    cell_area = mesh["cell_area"].values if "cell_area" in mesh else None
    depth_bnds = mesh["depth_bnds"].values if "depth_bnds" in mesh else None
    mesh.close()

    if cell_area is None or depth_bnds is None:
        raise ValueError("Mesh must contain 'cell_area' and 'depth_bnds'")

    dz = np.diff(depth_bnds)

    # Detect dimensions
    vertical_dim = None
    for dim in ["nz1", "nz", "depth", "lev"]:
        if dim in data.dims:
            vertical_dim = dim
            break
    horizontal_dim = None
    for dim in ["nod2", "ncells", "node"]:
        if dim in data.dims:
            horizontal_dim = dim
            break

    if vertical_dim is None or horizontal_dim is None:
        raise ValueError(f"Cannot identify dims. Available: {list(data.dims)}")

    # Load salinity if available for full steric computation
    salt_file = rule.get("salt_file")
    if salt_file:
        salt_ds = xr.open_dataset(salt_file)
        salt_var = rule.get("salt_variable", "salt")
        salt = salt_ds[salt_var]
    else:
        # Assume constant salinity of 35 psu for thermosteric-only
        salt = xr.full_like(data, 35.0)
        logger.warning("No salt_file specified, using constant S=35 for thermosteric computation")

    # Build thickness and area arrays
    nz = data.sizes[vertical_dim]
    thickness = xr.DataArray(dz[:nz], dims=[vertical_dim])
    area = xr.DataArray(cell_area, dims=[horizontal_dim])

    # Compute pressure from depth
    pressure = xr.DataArray(depth_bnds[:nz], dims=[vertical_dim])

    # Reference state: time-mean temperature (or use first timestep)
    temp_ref = data.mean(dim="time") if "time" in data.dims else data

    # Compute density for actual and reference states
    SA = gsw.SA_from_SP(salt, pressure, 0, 0)
    CT = gsw.CT_from_pt(SA, data)
    CT_ref = gsw.CT_from_pt(SA, temp_ref)

    rho_actual = gsw.rho(SA, CT, pressure)
    rho_ref = gsw.rho(SA, CT_ref, pressure)

    # Steric height anomaly per column:
    # delta_eta = -1/rho_0 * integral((rho - rho_ref) * dz)
    delta_rho = rho_actual - rho_ref
    steric_height = (-1.0 / rho_0) * (delta_rho * thickness).sum(dim=vertical_dim)

    # Global area-weighted mean
    total_area = area.sum()
    zostoga = (steric_height * area).sum(dim=horizontal_dim) / total_area

    zostoga.name = "zostoga"
    zostoga.attrs = {
        "units": "m",
        "standard_name": "global_average_thermosteric_sea_level_change",
        "long_name": "Global Average Thermosteric Sea Level Change",
        "processing_note": f"Computed from temperature anomaly relative to time-mean. rho_0={rho_0}",
    }
    return zostoga


# ============================================================
# Vertical integration step
# ============================================================


def vertical_integrate(
    data: xr.DataArray,
    rule,
    thickness_var: Optional[str] = None,
    vertical_dim: Optional[str] = None,
    update_attrs: bool = True,
) -> xr.DataArray:
    """
    Vertically integrate a 3D field over depth/pressure.

    General-purpose vertical integration for any 3D ocean/atmosphere variable.
    Computes weighted sum over vertical dimension using layer thickness.

    Parameters
    ----------
    data : xr.DataArray
        3D field to integrate (e.g., lon, lat, depth, time)
    rule : Rule
        Rule object containing processing parameters. Can specify:
        - thickness_var: Name of thickness coordinate/variable
        - vertical_dim: Name of vertical dimension to integrate over
        - integration_attrs: Dict of attributes to set on result
    vertical_dim : str, optional
        Name of vertical dimension. If None, auto-detect from common names.
    thickness_var : str, optional
        Name of thickness variable/coordinate. If None, auto-detect.
    update_attrs : bool, default True
        Whether to update attributes with integration metadata

    Returns
    -------
    xr.DataArray
        Vertically integrated field (2D or 3D if time dimension exists)

    Notes
    -----
    Auto-detects vertical dimension from common names:
    - Ocean: 'depth', 'lev', 'nz1', 'nod3D_below_nod2D', 'nz'
    - Atmosphere: 'plev', 'level', 'height'

    Thickness detection priority:
    1. User-specified thickness_var
    2. Rule-specified thickness coordinate
    3. Dimension bounds (e.g., depth_bnds)
    4. Standard thickness variables (thkcello, dz, etc.)
    5. Coordinate differences (fallback)
    """
    # Get parameters from rule if available
    thickness_var = thickness_var or rule.get("thickness_var", None)
    vertical_dim = vertical_dim or rule.get("vertical_dim", None)
    integration_attrs = rule.get("integration_attrs", {})

    # Identify the vertical dimension
    if vertical_dim is None:
        common_vertical_dims = [
            "depth",
            "lev",
            "plev",
            "level",
            "height",
            "nz1",
            "nod3D_below_nod2D",
            "nz",
            "pressure",
        ]
        for dim in common_vertical_dims:
            if dim in data.dims:
                vertical_dim = dim
                logger.info(f"Auto-detected vertical dimension: {vertical_dim}")
                break

    if vertical_dim is None or vertical_dim not in data.dims:
        raise ValueError(
            f"Could not identify vertical dimension. "
            f"Available dims: {list(data.dims)}. "
            f"Specify 'vertical_dim' in rule or function argument."
        )

    # Get layer thickness
    thickness = None

    # Priority 1: User-specified thickness variable
    if thickness_var:
        if thickness_var in data.coords:
            thickness = data.coords[thickness_var]
            logger.info(f"Using thickness from coordinate: {thickness_var}")
        elif thickness_var in data.attrs:
            logger.warning(f"Thickness variable {thickness_var} in attrs but not coords")

    # Priority 2: Bounds-based thickness
    if thickness is None:
        for bounds_suffix in ["_bnds", "_bounds"]:
            bounds_name = f"{vertical_dim}{bounds_suffix}"
            if bounds_name in data.coords:
                bounds = data.coords[bounds_name]
                thickness = abs(bounds[..., 1] - bounds[..., 0])
                logger.info(f"Computing thickness from bounds: {bounds_name}")
                break

    # Priority 3: Standard thickness variables
    if thickness is None:
        thickness_candidates = ["thkcello", "dz", "thickness", "layer_thickness"]
        for var in thickness_candidates:
            if var in data.coords:
                thickness = data.coords[var]
                logger.info(f"Using standard thickness variable: {var}")
                break

    # Priority 4: Coordinate differences (fallback)
    if thickness is None:
        import numpy as np

        logger.warning(
            f"No thickness information found for {vertical_dim}. "
            f"Computing from coordinate differences (may be inaccurate for irregular grids)."
        )
        coord_vals = data.coords[vertical_dim].values
        diffs = np.abs(np.diff(coord_vals))
        # Pad last element to match original dimension size
        thickness_vals = np.append(diffs, diffs[-1])
        thickness = xr.DataArray(thickness_vals, dims=[vertical_dim])

    # Perform vertical integration: (data * thickness) summed over vertical dimension
    integrated = (data * thickness).sum(dim=vertical_dim, keep_attrs=True)

    # Preserve the variable name
    integrated.name = data.name

    # Update attributes
    if update_attrs:
        # Preserve original attributes
        for key, value in data.attrs.items():
            if key not in ["long_name", "standard_name", "units", "cell_methods"]:
                integrated.attrs[key] = value

        # Add/update integration-specific attributes
        integrated.attrs["cell_methods"] = (
            f"{vertical_dim}: sum " + data.attrs.get("cell_methods", "").replace(f"{vertical_dim}: mean", "").strip()
        )

        # Apply custom attributes from rule if provided
        for key, value in integration_attrs.items():
            integrated.attrs[key] = value

        # Add processing note if not present
        if "processing_note" not in integrated.attrs:
            integrated.attrs["processing_note"] = f"Vertically integrated over {vertical_dim} dimension"

    return integrated
