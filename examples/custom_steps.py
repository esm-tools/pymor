"""
Custom processing steps for pycmor pipelines.

Steps are organized by reusability:
- Generic steps (load_gridfile): work with any model/realm
- Ocean fx steps (compute_deptho, etc.): FESOM-specific but pattern is reusable
- Vertical integration: generic ocean/atmosphere
"""

import glob as _glob
import logging
import os as _os
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
# Sea ice steps
# ============================================================


def fraction_to_percent(data, rule):
    """
    Convert a fraction (0-1) to percentage (0-100).

    Generic step — works for any variable stored as fraction
    that CMIP expects as percentage (siconc, sftof, etc.).
    """
    result = data * 100.0
    result.attrs = data.attrs.copy()
    result.attrs["units"] = "%"
    result.name = data.name
    return result


def compute_sitimefrac(data, rule):
    """
    Compute fraction of time steps with sea ice present.

    From monthly sea ice concentration, sitimefrac is 1 where
    siconc > 0, and 0 otherwise. For monthly data this is a
    binary field (ice present that month or not).

    For accurate sitimefrac, daily or sub-daily siconc is needed.
    With monthly data this is an approximation.
    """
    result = xr.where(data > 0, 1.0, 0.0)
    result.attrs = {
        "units": "1",
        "standard_name": "fraction_of_time_with_sea_ice_area_fraction_above_threshold",
        "long_name": "Fraction of Time Steps with Sea Ice",
        "processing_note": "Computed from monthly siconc; 1 where siconc>0, 0 otherwise",
    }
    result.name = "sitimefrac"
    return result


# ============================================================
# Sea ice post-processing steps — computed from available output
# ============================================================


def compute_siflcondtop(data, rule):
    """
    Compute conductive heat flux at ice surface.

    siflcondtop = k_ice * (T_base - T_surface) / h_ice

    Positive downward (into the ice, i.e. when surface is colder
    than base). T_base is the freezing point computed from SSS.

    Primary input (data) is ist (ice surface temperature, K).
    Rule attributes:
      - sss_file: path to SSS file (for freezing point)
      - sss_variable: variable name (default: 'sss')
      - hice_file: path to h_ice file
      - hice_variable: variable name (default: 'h_ice')
      - k_ice: thermal conductivity of ice (default: 2.1656 W/m/K, from namelist.ice con=)
    """
    k_ice = float(rule.get("k_ice", 2.1656))

    sss_file = rule.get("sss_file")
    hice_file = rule.get("hice_file")
    if sss_file is None or hice_file is None:
        raise ValueError("Rule must specify 'sss_file' and 'hice_file'")

    ds_sss = xr.open_dataset(sss_file)
    sss = ds_sss[rule.get("sss_variable", "sss")]
    ds_sss.close()

    ds_hice = xr.open_dataset(hice_file)
    h_ice = ds_hice[rule.get("hice_variable", "h_ice")]
    ds_hice.close()

    # Freezing point at ice base
    t_base = -0.054 * sss + 273.15

    # Avoid division by zero where ice is absent
    h_safe = xr.where(h_ice > 0.01, h_ice, np.nan)

    result = k_ice * (t_base - data) / h_safe
    result.attrs = {
        "units": "W m-2",
        "standard_name": "sea_ice_surface_net_downward_conductive_heat_flux",
        "long_name": "Net Conductive Heat Flux in Sea Ice at the Surface",
        "processing_note": f"k_ice={k_ice}, T_base=freezing_point(SSS), T_surface=ist",
    }
    result.name = "siflcondtop"
    return result


def compute_sihc(data, rule):
    """
    Compute sea ice heat content per unit area.

    sihc = rho_ice * h_ice * (c_ice * (T_mean - T_melt) - L_f)

    where T_mean is approximated as average of surface and basal
    temperature: (ist + T_freeze) / 2.

    This is always negative (energy required to melt ice).

    Primary input (data) is h_ice.
    Rule attributes:
      - ist_file: path to ice surface temperature file
      - ist_variable: variable name (default: 'ist')
      - sss_file: path to SSS file (for freezing point at base)
      - sss_variable: variable name (default: 'sss')
      - rho_ice: ice density (default: 910.0 kg/m3)
      - c_ice: specific heat of ice (default: 2090.0 J/kg/K)
      - L_f: latent heat of fusion (default: 334000.0 J/kg)
    """
    rho_ice = float(rule.get("rho_ice", 910.0))
    c_ice = float(rule.get("c_ice", 2090.0))
    L_f = float(rule.get("L_f", 334000.0))

    ist_file = rule.get("ist_file")
    sss_file = rule.get("sss_file")
    if ist_file is None or sss_file is None:
        raise ValueError("Rule must specify 'ist_file' and 'sss_file'")

    ds_ist = xr.open_dataset(ist_file)
    ist = ds_ist[rule.get("ist_variable", "ist")]
    ds_ist.close()

    ds_sss = xr.open_dataset(sss_file)
    sss = ds_sss[rule.get("sss_variable", "sss")]
    ds_sss.close()

    # Freezing point at ice base
    t_base = -0.054 * sss + 273.15
    # Mean ice temperature (linear profile approximation)
    t_mean = (ist + t_base) / 2.0
    # Melting point in K
    t_melt = 273.15

    # Heat content: sensible + latent (latent dominates, result is negative)
    result = rho_ice * data * (c_ice * (t_mean - t_melt) - L_f)
    result.attrs = {
        "units": "J m-2",
        "standard_name": "integral_of_sea_ice_temperature_wrt_depth_expressed_as_heat_content",
        "long_name": "Sea-Ice Heat Content",
        "processing_note": f"rho_ice={rho_ice}, c_ice={c_ice}, L_f={L_f}, T_mean=(ist+T_freeze)/2",
    }
    result.name = "sihc"
    return result


def compute_sisnhc(data, rule):
    """
    Compute snow heat content per unit area on sea ice.

    sisnhc ≈ rho_snow * h_snow * (c_snow * (T_snow - T_melt) - L_f)

    Snow on sea ice is typically near 0°C, so T_snow ≈ T_melt and
    the sensible term vanishes. The dominant term is latent heat:
    sisnhc ≈ -rho_snow * L_f * h_snow (always negative).

    Primary input (data) is h_snow.
    Rule attributes:
      - rho_snow: snow density (default: 330.0 kg/m3)
      - L_f: latent heat of fusion (default: 334000.0 J/kg)
    """
    rho_snow = float(rule.get("rho_snow", 330.0))
    L_f = float(rule.get("L_f", 334000.0))

    # Dominant term: latent heat (sensible ≈ 0 since T_snow ≈ T_melt)
    result = -rho_snow * L_f * data
    result.attrs = {
        "units": "J m-2",
        "standard_name": "integral_of_snow_temperature_wrt_depth_expressed_as_heat_content",
        "long_name": "Snow Heat Content",
        "processing_note": f"sisnhc = -rho_snow*L_f*h_snow, rho_snow={rho_snow}, L_f={L_f}",
    }
    result.name = "sisnhc"
    return result


def compute_sitempbot(data, rule):
    """
    Compute temperature at ice-ocean interface (freezing point).

    T_freeze = -0.054 * SSS + 273.15 K (linear approximation).

    Primary input (data) is SSS (sea surface salinity, in psu).
    Returns temperature in K.
    """
    result = -0.054 * data + 273.15
    result.attrs = {
        "units": "K",
        "standard_name": "sea_ice_basal_temperature",
        "long_name": "Temperature at Ice-Ocean Interface",
        "processing_note": "Computed as freezing point: T_f = -0.054 * SSS + 273.15",
    }
    result.name = "sitempbot"
    return result


def compute_sifb(data, rule):
    """
    Compute sea ice freeboard from ice and snow thickness.

    freeboard = h_ice * (1 - rho_ice/rho_water) - h_snow * rho_snow/rho_water

    Primary input (data) is h_ice.
    Rule attributes:
      - snow_file: path to h_snow file
      - snow_variable: variable name (default: 'h_snow')
      - rho_ice: ice density (default: 910.0 kg/m3)
      - rho_snow: snow density (default: 330.0 kg/m3)
      - rho_water: seawater density (default: 1025.0 kg/m3)
    """
    rho_ice = float(rule.get("rho_ice", 910.0))
    rho_snow = float(rule.get("rho_snow", 330.0))
    rho_water = float(rule.get("rho_water", 1025.0))

    snow_file = rule.get("snow_file")
    if snow_file is None:
        raise ValueError("Rule must specify 'snow_file' for compute_sifb")

    ds = xr.open_dataset(snow_file)
    snow_var = rule.get("snow_variable", "h_snow")
    h_snow = ds[snow_var]
    ds.close()

    result = data * (1.0 - rho_ice / rho_water) - h_snow * rho_snow / rho_water
    result.attrs = {
        "units": "m",
        "standard_name": "sea_ice_freeboard",
        "long_name": "Sea-Ice Freeboard",
        "processing_note": f"freeboard = h_ice*(1-{rho_ice}/{rho_water}) - h_snow*{rho_snow}/{rho_water}",
    }
    result.name = "sifb"
    return result


def compute_constant_field(data, rule):
    """
    Replace data values with a constant, preserving shape and coordinates.

    Used for fields that are constant in the model configuration,
    e.g. drag coefficients.

    Rule attributes:
      - constant_value: float (required)
      - constant_units: str (optional)
    """
    value = float(rule.get("constant_value"))
    if value is None:
        raise ValueError("Rule must specify 'constant_value'")
    result = xr.full_like(data, value)
    result.attrs = data.attrs.copy()
    constant_units = rule.get("constant_units")
    if constant_units:
        result.attrs["units"] = constant_units
    result.name = data.name
    return result


def integrate_over_hemisphere(data, rule):
    """
    Area-weighted hemisphere integral of any 2D field.

    result = sum(data * cell_area) for nodes in the selected hemisphere.

    Generic step — works for any variable that needs hemisphere
    integration: snow mass, ice volume, ice area, etc.

    Rule attributes:
      - grid_file: path to mesh file (for cell_area and lat)
      - hemisphere: 'N' or 'S'
    """
    grid_file = rule.get("grid_file")
    hemisphere = rule.get("hemisphere", "N")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for integrate_over_hemisphere")

    mesh = xr.open_dataset(grid_file)

    # Get cell area
    if "cell_area" in mesh:
        cell_area = mesh["cell_area"]
    elif "cluster_area" in mesh:
        cell_area = mesh["cluster_area"]
    else:
        raise ValueError("Mesh must contain 'cell_area' or 'cluster_area'")

    # Get latitude for hemisphere selection
    if "lat" in mesh:
        lat = mesh["lat"]
    elif "latitude" in mesh:
        lat = mesh["latitude"]
    else:
        raise ValueError("Mesh must contain 'lat' or 'latitude'")
    mesh.close()

    # Select hemisphere
    if hemisphere.upper() == "N":
        mask = lat >= 0
    else:
        mask = lat < 0

    # Integrate: sum(data * cell_area) over hemisphere nodes
    horizontal_dim = None
    for dim in ["nod2", "ncells", "node"]:
        if dim in data.dims:
            horizontal_dim = dim
            break
    if horizontal_dim is None:
        raise ValueError(f"Cannot identify horizontal dim. Available: {list(data.dims)}")

    result = (data * cell_area * mask).sum(dim=horizontal_dim)
    result.attrs = data.attrs.copy()
    result.name = data.name
    return result


# ============================================================
# Melt pond steps
# ============================================================


def compute_simpeffconc(data, rule):
    """
    Compute effective (radiatively-active) melt pond area fraction.

    Effective pond fraction = pond area not covered by a refrozen lid.
    Where the lid fully covers the pond depth, the pond is not
    radiatively active.

    simpeffconc = apnd * max(0, 1 - ipnd/hpnd) * 100

    Primary input (data) is apnd (melt pond area fraction, 0-1).
    Rule attributes:
      - ipnd_file: path to ice lid thickness file
      - ipnd_variable: variable name (default: 'ipnd')
      - hpnd_file: path to pond depth file
      - hpnd_variable: variable name (default: 'hpnd')
    """
    ipnd_file = rule.get("ipnd_file")
    hpnd_file = rule.get("hpnd_file")
    if ipnd_file is None or hpnd_file is None:
        raise ValueError("Rule must specify 'ipnd_file' and 'hpnd_file'")

    ds_ipnd = xr.open_dataset(ipnd_file)
    ipnd = ds_ipnd[rule.get("ipnd_variable", "ipnd")]
    ds_ipnd.close()

    ds_hpnd = xr.open_dataset(hpnd_file)
    hpnd = ds_hpnd[rule.get("hpnd_variable", "hpnd")]
    ds_hpnd.close()

    # Lid fraction: ipnd/hpnd, clamped to [0, 1]
    # Where hpnd is 0, there's no pond so effective fraction is 0
    hpnd_safe = xr.where(hpnd > 0, hpnd, np.nan)
    lid_fraction = np.clip(ipnd / hpnd_safe, 0, 1).fillna(1.0)

    # Effective fraction = open pond area (not lidded), convert to %
    result = data * (1.0 - lid_fraction) * 100.0
    result.attrs = {
        "units": "%",
        "standard_name": "area_fraction",
        "long_name": "Fraction of Sea Ice Covered by Effective Melt Pond",
        "processing_note": "simpeffconc = apnd * (1 - ipnd/hpnd) * 100",
    }
    result.name = "simpeffconc"
    return result


# ============================================================
# Generic scaling step — reusable across models and realms
# ============================================================


def scale_by_constant(data, rule):
    """
    Multiply data by a constant factor from rule.scale_factor.

    Generic step for unit conversions that are a simple multiplication,
    e.g. m/s → kg m-2 s-1 (multiply by density).

    Rule attributes:
      - scale_factor: float, the multiplicative factor (required)
      - scaled_units: str, units after scaling (optional, updates attrs)
    """
    factor = float(rule.get("scale_factor"))
    if factor is None:
        raise ValueError("Rule must specify 'scale_factor' for scale_by_constant step")
    result = data * factor
    result.attrs = data.attrs.copy()
    scaled_units = rule.get("scaled_units")
    if scaled_units:
        result.attrs["units"] = scaled_units
    result.name = data.name
    return result


# ============================================================
# Generic compute steps — reusable across models and realms
# ============================================================


def compute_square(data, rule):
    """
    Square the input field.

    Useful for variance-related diagnostics (tossq, sossq, zossq, mlotstsq).

    Rule attributes (optional):
      - squared_units: str, units after squaring (e.g. "degC2", "m2")
    """
    result = data * data
    result.attrs = data.attrs.copy()
    squared_units = rule.get("squared_units")
    if squared_units:
        result.attrs["units"] = squared_units
    result.name = data.name
    return result


def extract_bottom(data, rule):
    """
    Extract the bottom-of-column value from a 3D field.

    Uses the mesh bottom index to select the deepest valid value at each
    horizontal point. Produces a 2D (+ time) field from a 3D input.

    Rule attributes:
      - grid_file: path to mesh file containing bottom index info
      - vertical_dim: name of vertical dimension (auto-detected if not given)
    """
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for extract_bottom step")

    mesh = xr.open_dataset(grid_file)

    # Auto-detect vertical dimension
    vertical_dim = rule.get("vertical_dim")
    if vertical_dim is None:
        for dim in ["nz1", "depth", "lev", "nz"]:
            if dim in data.dims:
                vertical_dim = dim
                break
    if vertical_dim is None:
        raise ValueError(f"Cannot find vertical dimension in {list(data.dims)}")

    # Get number of levels per node from mesh
    # FESOM meshes typically have 'nlevels' or 'nlevels_nod2D' (1-based count)
    if "nlevels_nod2D" in mesh:
        bottom_idx = mesh["nlevels_nod2D"].values - 2  # 0-based, last valid midpoint
    elif "nlevels" in mesh:
        bottom_idx = mesh["nlevels"].values - 2
    else:
        mesh.close()
        raise ValueError("Mesh file must contain 'nlevels_nod2D' or 'nlevels'")
    mesh.close()

    # Clamp to valid range
    nz = data.sizes[vertical_dim]
    bottom_idx = np.clip(bottom_idx, 0, nz - 1)

    # Extract bottom values using advanced indexing
    # Convert bottom_idx to DataArray for .isel compatibility
    horizontal_dim = next(d for d in data.dims if d not in [vertical_dim, "time"])
    idx_da = xr.DataArray(bottom_idx, dims=[horizontal_dim])
    result = data.isel({vertical_dim: idx_da})

    result.attrs = data.attrs.copy()
    result.name = data.name
    return result


def extract_surface(data, rule):
    """
    Extract the surface (top) value from a 3D field.

    Selects index 0 along the vertical dimension to produce a
    2D (+ time) field from a 3D input.

    Rule attributes (optional):
      - vertical_dim: name of vertical dimension (auto-detected if not given)
    """
    vertical_dim = rule.get("vertical_dim")
    if vertical_dim is None:
        for dim in ["nz1", "depth", "lev", "nz"]:
            if dim in data.dims:
                vertical_dim = dim
                break
    if vertical_dim is None:
        raise ValueError(f"Cannot find vertical dimension in {list(data.dims)}")

    result = data.isel({vertical_dim: 0})
    result.attrs = data.attrs.copy()
    result.name = data.name
    return result


def compute_surface_pressure(data, rule):
    """
    Compute sea water pressure at sea surface from SSH.

    pso = rho_0 * g * ssh  [Pa]

    For a Boussinesq model, surface pressure is the weight of the
    water column above the geoid approximated by rho_0 * g * ssh.

    Rule attributes (optional):
      - reference_density: float (default 1025.0 kg/m3)
      - gravity: float (default 9.80665 m/s2)
    """
    rho_0 = float(rule.get("reference_density", 1025.0))
    g = float(rule.get("gravity", 9.80665))
    result = rho_0 * g * data
    result.attrs = data.attrs.copy()
    result.attrs["units"] = "Pa"
    result.name = data.name
    return result


# ============================================================
# Sea ice multi-variable compute steps
# These load a second variable from an auxiliary file specified
# in rule attributes.
# ============================================================


def compute_sispeed(data, rule):
    """
    Compute sea ice speed from X and Y velocity components.

    sispeed = sqrt(uice² + vice²)

    Primary input (data) is one velocity component.
    The other component is loaded from rule.second_input_file.

    Rule attributes:
      - second_input_file: path to the other velocity component file
      - second_variable: variable name in that file (default: auto-detect)
    """
    second_file = rule.get("second_input_file")
    if second_file is None:
        raise ValueError("Rule must specify 'second_input_file' for compute_sispeed")

    ds2 = xr.open_dataset(second_file)
    second_var = rule.get("second_variable")
    if second_var and second_var in ds2:
        v2 = ds2[second_var]
    else:
        # Auto-detect: take first non-coordinate variable
        data_vars = [v for v in ds2.data_vars if v not in ds2.coords]
        v2 = ds2[data_vars[0]]
    ds2.close()

    result = np.sqrt(data**2 + v2**2)
    result.attrs = {
        "units": "m s-1",
        "standard_name": "sea_ice_speed",
        "long_name": "Sea-Ice Speed",
    }
    result.name = "sispeed"
    return result


def compute_ice_mass_transport(data, rule):
    """
    Compute sea ice mass transport: velocity × mass per area.

    ice_mass_transport = velocity_component × m_ice

    Rule attributes:
      - mice_file: path to m_ice file
      - mice_variable: variable name (default: 'm_ice')
    """
    mice_file = rule.get("mice_file")
    if mice_file is None:
        raise ValueError("Rule must specify 'mice_file' for compute_ice_mass_transport")

    ds = xr.open_dataset(mice_file)
    mice_var = rule.get("mice_variable", "m_ice")
    m_ice = ds[mice_var]
    ds.close()

    result = data * m_ice
    result.attrs = data.attrs.copy()
    result.attrs["units"] = "kg s-1"
    result.name = data.name
    return result


def compute_sistressave(data, rule):
    """
    Compute average normal sea ice stress from mEVP stress tensor.

    sistressave = (sigma_11 + sigma_22) / 2

    Primary input (data) is sgm11 dataset.
    Rule attributes:
      - sgm22_file: path to sgm22 file
      - sgm22_variable: variable name (default: 'sgm22')
    """
    sgm22_file = rule.get("sgm22_file")
    if sgm22_file is None:
        raise ValueError("Rule must specify 'sgm22_file' for compute_sistressave")

    ds = xr.open_dataset(sgm22_file)
    sgm22_var = rule.get("sgm22_variable", "sgm22")
    sgm22 = ds[sgm22_var]
    ds.close()

    result = (data + sgm22) / 2.0
    result.attrs = {
        "units": "N m-1",
        "standard_name": "average_normal_stress_in_sea_ice",
        "long_name": "Average Normal Stress in Sea Ice",
    }
    result.name = "sistressave"
    return result


def compute_sistressmax(data, rule):
    """
    Compute maximum shear stress from mEVP stress tensor.

    sistressmax = sqrt(((sigma_11 - sigma_22) / 2)² + sigma_12²)

    Primary input (data) is sgm11 dataset.
    Rule attributes:
      - sgm22_file: path to sgm22 file
      - sgm12_file: path to sgm12 file
    """
    sgm22_file = rule.get("sgm22_file")
    sgm12_file = rule.get("sgm12_file")
    if sgm22_file is None or sgm12_file is None:
        raise ValueError("Rule must specify 'sgm22_file' and 'sgm12_file'")

    ds22 = xr.open_dataset(sgm22_file)
    sgm22 = ds22[rule.get("sgm22_variable", "sgm22")]
    ds22.close()

    ds12 = xr.open_dataset(sgm12_file)
    sgm12 = ds12[rule.get("sgm12_variable", "sgm12")]
    ds12.close()

    result = np.sqrt(((data - sgm22) / 2.0) ** 2 + sgm12**2)
    result.attrs = {
        "units": "N m-1",
        "standard_name": "maximum_shear_stress_in_sea_ice",
        "long_name": "Maximum Shear Stress in Sea Ice",
    }
    result.name = "sistressmax"
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


# ============================================================
# Volume cell steps (volcello)
# ============================================================


def compute_volcello_fx(data, rule):
    """
    Compute static ocean grid-cell volume from mesh geometry.

    volcello = cell_area * layer_thickness

    Input (data) is loaded from the grid/mesh file (via load_gridfile step).
    Expects the mesh Dataset to contain cell_area (or cluster_area)
    and depth_bnds for layer thickness computation.

    Rule attributes:
      - (none required beyond grid_file already used by load_gridfile)
    """
    if "cell_area" in data:
        cell_area = data["cell_area"]
    elif "cluster_area" in data:
        cell_area = data["cluster_area"]
    else:
        raise ValueError("Mesh must contain 'cell_area' or 'cluster_area'")

    if "depth_bnds" not in data:
        raise ValueError("Mesh must contain 'depth_bnds' for layer thickness")

    bnds = data["depth_bnds"].values
    thickness = np.abs(np.diff(bnds, axis=-1)).squeeze()
    dz = xr.DataArray(thickness, dims=["nz1"])

    result = cell_area * dz
    result.attrs = {"units": "m3", "standard_name": "ocean_volume", "long_name": "Ocean Grid-Cell Volume"}
    result.name = "volcello"
    return result


def compute_volcello_time(data, rule):
    """
    Compute time-varying ocean grid-cell volume from layer thickness.

    volcello = hnode * cell_area

    Input (data) is hnode (time-varying layer thickness per node per level).
    cell_area is loaded from the mesh file.

    Rule attributes:
      - grid_file: path to mesh file (for cell_area)
    """
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for compute_volcello_time")

    mesh = xr.open_dataset(grid_file)
    if "cell_area" in mesh:
        cell_area = mesh["cell_area"]
    elif "cluster_area" in mesh:
        cell_area = mesh["cluster_area"]
    else:
        mesh.close()
        raise ValueError("Mesh must contain 'cell_area' or 'cluster_area'")
    mesh.close()

    result = data * cell_area
    result.attrs = data.attrs.copy()
    result.attrs["units"] = "m3"
    result.attrs["standard_name"] = "ocean_volume"
    result.attrs["long_name"] = "Ocean Grid-Cell Volume"
    result.name = data.name
    return result


# ============================================================
# Atmosphere derived-variable steps
# These compute CMOR variables that require combining two or
# more IFS output fields (e.g. wind speed from u/v components,
# humidity from dewpoint + temperature/pressure).
#
# Secondary inputs are loaded via glob patterns specified in
# rule attributes, using xr.open_mfdataset for multi-file
# (yearly split) atmosphere output.
# ============================================================


def _load_secondary_mf(rule, path_key, pattern_key, variable_key):
    """Load a secondary input variable from a glob pattern of files.

    Parameters
    ----------
    rule : Rule
        The pycmor rule object.
    path_key : str
        Rule attribute name for the directory path.
    pattern_key : str
        Rule attribute name for the file glob pattern.
    variable_key : str
        Rule attribute name for the variable name inside the files.

    Returns
    -------
    xr.DataArray
    """
    path = rule.get(path_key)
    pattern = rule.get(pattern_key)
    if path is None or pattern is None:
        raise ValueError(f"Rule must specify '{path_key}' and '{pattern_key}'")
    files = sorted(_glob.glob(_os.path.join(path, pattern)))
    if not files:
        raise FileNotFoundError(f"No files matching {_os.path.join(path, pattern)}")
    ds = xr.open_mfdataset(files)
    var_name = rule.get(variable_key)
    if var_name and var_name in ds:
        result = ds[var_name]
    else:
        data_vars = [v for v in ds.data_vars if v not in ds.coords]
        result = ds[data_vars[0]]
    return result


def compute_sfcwind(data, rule):
    """
    Compute near-surface wind speed from U and V components.

    sfcWind = sqrt(10u² + 10v²)

    Primary input (data) is 10u (eastward 10m wind).
    The V component is loaded from rule attributes.

    Rule attributes:
      - second_input_path: directory containing V-component files
      - second_input_pattern: glob pattern for V-component files
      - second_variable: variable name in V files (default: auto-detect)
    """
    v10 = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")
    result = np.sqrt(data**2 + v10**2)
    result.attrs = {
        "units": "m s-1",
        "standard_name": "wind_speed",
        "long_name": "Near-Surface Wind Speed",
    }
    result.name = "sfcWind"
    return result


def compute_hurs(data, rule):
    """
    Compute near-surface relative humidity from temperature and dewpoint.

    Uses the Magnus formula:
      RH = 100 * exp(b*Td/(c+Td)) / exp(b*T/(c+T))

    where T and Td are in Celsius, b = 17.625, c = 243.04.

    Primary input (data) is 2t (2m temperature, K).
    Dewpoint is loaded from rule attributes.

    Rule attributes:
      - second_input_path: directory containing dewpoint files
      - second_input_pattern: glob pattern for dewpoint files
      - second_variable: variable name in dewpoint files
    """
    td_K = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")

    # Convert K -> °C
    t_C = data - 273.15
    td_C = td_K - 273.15

    # Magnus formula constants (Alduchov and Eskridge, 1996)
    b = 17.625
    c = 243.04

    result = 100.0 * np.exp(b * td_C / (c + td_C)) / np.exp(b * t_C / (c + t_C))

    # Clip to physical range
    result = result.clip(0, 100)

    result.attrs = {
        "units": "%",
        "standard_name": "relative_humidity",
        "long_name": "Near-Surface Relative Humidity",
    }
    result.name = "hurs"
    return result


def compute_huss(data, rule):
    """
    Compute near-surface specific humidity from dewpoint and surface pressure.

    Uses Tetens formula for saturation vapour pressure at dewpoint:
      e = 611.2 * exp(17.67 * Td / (Td + 243.5))

    Then specific humidity:
      q = 0.622 * e / (p - 0.378 * e)

    Primary input (data) is 2d (2m dewpoint temperature, K).
    Surface pressure is loaded from rule attributes.

    Rule attributes:
      - second_input_path: directory containing surface pressure files
      - second_input_pattern: glob pattern for surface pressure files
      - second_variable: variable name in pressure files
    """
    sp = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")

    # Dewpoint in Celsius
    td_C = data - 273.15

    # Saturation vapour pressure at dewpoint (Tetens formula)
    e = 611.2 * np.exp(17.67 * td_C / (td_C + 243.5))

    result = 0.622 * e / (sp - 0.378 * e)
    result.attrs = {
        "units": "1",
        "standard_name": "specific_humidity",
        "long_name": "Near-Surface Specific Humidity",
    }
    result.name = "huss"
    return result


def compute_clwvi(data, rule):
    """
    Compute condensed water path (liquid + ice).

    clwvi = tclw + tciw

    Primary input (data) is tclw (total column cloud liquid water).
    Ice water path is loaded from rule attributes.

    Rule attributes:
      - second_input_path: directory containing tciw files
      - second_input_pattern: glob pattern for tciw files
      - second_variable: variable name in tciw files
    """
    tciw = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")
    result = data + tciw
    result.attrs = {
        "units": "kg m-2",
        "standard_name": "atmosphere_mass_content_of_cloud_condensed_water",
        "long_name": "Condensed Water Path",
    }
    result.name = "clwvi"
    return result


# ============================================================
# Land surface derived-variable steps
# ============================================================


def compute_snc(data, rule):
    """
    Compute snow area fraction from snow depth (water equivalent).

    Uses a saturation curve: snc = min(100, sd_we / sd_crit * 100)
    where sd_crit = 0.015 m water equivalent (~5 cm fresh snow).

    Primary input (data) is sd (snow depth, m water equivalent).
    """
    sd_crit = 0.015  # m water equivalent threshold for full cover
    result = (data / sd_crit * 100).clip(min=0, max=100)
    result.attrs = {
        "units": "%",
        "standard_name": "surface_snow_area_fraction",
        "long_name": "Snow Area Fraction",
    }
    result.name = "snc"
    return result


def compute_areacella(data, rule):
    """
    Compute atmospheric grid cell area from latitude/longitude.

    Uses the spherical Earth formula:
      area = R^2 * delta_lon * |sin(lat+dlat/2) - sin(lat-dlat/2)|

    Primary input (data) is any field on the target grid (used for coords).
    """
    R = 6371000.0  # Earth radius in metres

    # Get lat/lon coordinates
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

    # Compute grid spacing
    dlat = np.abs(np.diff(lat_vals).mean())
    dlon = np.abs(np.diff(lon_vals).mean())

    # Cell area for each latitude band
    lat_upper = lat_vals + dlat / 2
    lat_lower = lat_vals - dlat / 2
    area_1d = R**2 * dlon * np.abs(np.sin(lat_upper) - np.sin(lat_lower))

    # Broadcast to 2D (lat, lon)
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
    }
    result.name = "areacella"
    return result


def compute_slthick(data, rule):
    """
    Generate HTESSEL soil layer thicknesses as a constant field.

    IFS HTESSEL has 4 soil layers with fixed thicknesses:
      Layer 1: 0.07 m (0-7 cm)
      Layer 2: 0.21 m (7-28 cm)
      Layer 3: 0.72 m (28-100 cm)
      Layer 4: 1.89 m (100-289 cm)

    Primary input (data) is ignored (any grid file will do).
    """
    thicknesses = np.array([0.07, 0.21, 0.72, 1.89])
    result = xr.DataArray(
        thicknesses,
        dims=["sdepth"],
        coords={"sdepth": np.arange(1, 5)},
    )
    result.attrs = {
        "units": "m",
        "standard_name": "cell_thickness",
        "long_name": "Thickness of Soil Layers",
    }
    result.name = "slthick"
    return result
