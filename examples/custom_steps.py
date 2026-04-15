"""
Custom processing steps for pycmor pipelines.

Steps are organized by reusability:
- Generic steps (load_gridfile): work with any model/realm
- Ocean fx steps (compute_deptho, etc.): FESOM-specific but pattern is reusable
- Vertical integration: generic ocean/atmosphere

Function index (keep this list in sync when adding/removing steps; helps avoid duplicates):

  Loaders / generic
    load_basin_mask, load_gridfile, _load_secondary_mf,
    load_lpjguess_monthly, load_lpjguess_yearly,
    load_lpjguess_yearly_lut, load_lpjguess_monthly_lut,
    sum_lpjguess_monthly_files

  Generic scaling / arithmetic / selection
    scale_by_constant, fraction_to_percent, compute_square,
    compute_constant_field, compute_temporal_diff,
    extract_bottom, extract_surface, extract_single_plevel,
    select_southern_hemisphere, integrate_over_hemisphere, vertical_integrate

  Ocean fx (FESOM mesh)
    compute_deptho, compute_sftof, compute_thkcello_fx,
    compute_masscello_fx, compute_volcello_fx, compute_volcello_time

  Ocean diagnostics
    compute_density, compute_zostoga, compute_msftbarot,
    compute_mass_transport, compute_salt_transport,
    compute_salt_transport_integrated, compute_heat_transport,
    compute_msftmz, compute_hfbasin, compute_sltbasin,
    _node_edge_length, _elem_geometry,
    _load_basin_nodes, _mesh_nodes, _elem_lat_area, _basin_lat_sum

  Sea ice
    compute_sitimefrac, compute_siflcondtop, compute_sihc,
    compute_sisnhc, compute_sisnhc_from_msnow, compute_snd_from_msnow,
    compute_sitempbot, compute_sifb, compute_simpeffconc,
    compute_sispeed, compute_ice_mass_transport,
    compute_sistressave, compute_sistressmax, compute_slthick

  Atmosphere
    compute_surface_pressure, compute_sfcwind, compute_hurs, compute_hur_ml,
    compute_huss, compute_clwvi, compute_snc, compute_areacella, compute_rtmt

  Land / LPJ-GUESS
    compute_fire_emission, compute_mrtws, compute_snd,
    compute_mrsow, compute_sftgif, compute_mrsofc, compute_rootd
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


def load_basin_mask(data, rule):
    """
    Load a FESOM basin mask file as an xarray Dataset.

    Reads the path from rule.basin_mask_file. Renames the horizontal
    dimension ``ncells`` (as used in the mask file) to ``nod2`` so the
    result matches FESOM output and downstream steps (map_dimensions,
    set_coordinates) treat it as a surface field on the unstructured mesh.
    """
    basin_file = rule.get("basin_mask_file")
    if basin_file is None:
        raise ValueError("Rule must specify 'basin_mask_file' for load_basin_mask step")
    logger.info(f"Loading basin mask file: {basin_file}")
    ds = xr.open_dataset(basin_file)
    if "ncells" in ds.dims:
        ds = ds.rename({"ncells": "nod2"})
    return ds


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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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

    # Align secondary data time coordinates with primary data.
    # If same length: just overwrite the coordinate to preserve DatetimeIndex type.
    # If different length (e.g. monthly h_ice vs daily ist): reindex with
    # forward-fill so monthly values are broadcast to daily timesteps.
    if "time" in data.dims and "time" in sss.dims:
        if len(sss.time) == len(data.time):
            sss = sss.assign_coords(time=data.time)
        else:
            sss = sss.reindex(time=data.time, method="ffill")

    if "time" in data.dims and "time" in h_ice.dims:
        if len(h_ice.time) == len(data.time):
            h_ice = h_ice.assign_coords(time=data.time)
        else:
            h_ice = h_ice.reindex(time=data.time, method="ffill")

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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
    return result


def compute_sisnhc_from_msnow(data, rule):
    """
    Compute daily snow heat content from m_snow and a_ice.

    FESOM outputs h_snow only at monthly frequency. For daily sisnhc,
    derive h_snow from daily m_snow (snow mass per area) and a_ice
    (ice concentration):

        h_snow = m_snow / (rho_snow * a_ice)
        sisnhc = -rho_snow * L_f * h_snow = -L_f * m_snow / a_ice

    Primary input (data) is m_snow (kg/m2).
    Secondary input a_ice loaded via rule attributes.

    Rule attributes:
      - second_input_path: directory containing a_ice files
      - second_input_pattern: glob pattern for a_ice files
      - second_variable: variable name (default: auto-detect)
      - rho_snow: snow density (default: 330.0 kg/m3, used only in note)
      - L_f: latent heat of fusion (default: 334000.0 J/kg)
    """
    rho_snow = float(rule.get("rho_snow", 330.0))
    L_f = float(rule.get("L_f", 334000.0))

    a_ice = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")

    # h_snow = m_snow / (rho_snow * a_ice), then sisnhc = -rho_snow * L_f * h_snow
    # Simplifies to: sisnhc = -L_f * m_snow / a_ice
    # Protect against division by zero where a_ice == 0
    a_ice_safe = a_ice.where(a_ice > 0, np.nan)
    result = -L_f * data / a_ice_safe
    result = result.fillna(0.0)

    result.attrs = {
        "units": "J m-2",
        "standard_name": "integral_of_snow_temperature_wrt_depth_expressed_as_heat_content",
        "long_name": "Snow Heat Content",
        "processing_note": (
            f"sisnhc = -L_f*m_snow/a_ice, rho_snow={rho_snow}, L_f={L_f}, " "derived from daily m_snow and a_ice"
        ),
    }
    result.name = rule.model_variable
    return result


def compute_snd_from_msnow(data, rule):
    """
    Compute daily snow depth on sea ice from m_snow and a_ice.

    FESOM outputs h_snow only at monthly frequency. For daily snd,
    derive from daily m_snow (snow mass per area) and a_ice
    (ice concentration):

        snd = m_snow / a_ice

    where m_snow is area-averaged snow mass [m water equiv] and a_ice
    is ice concentration [0-1]. Result is snow depth over ice [m].

    Primary input (data) is m_snow.
    Secondary input a_ice loaded via rule attributes.

    Rule attributes:
      - second_input_path: directory containing a_ice files
      - second_input_pattern: glob pattern for a_ice files
      - second_variable: variable name (default: auto-detect)
    """
    a_ice = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")

    # snd = m_snow / a_ice (snow depth over ice-covered fraction)
    # Protect against division by zero where a_ice == 0
    a_ice_safe = a_ice.where(a_ice > 0, np.nan)
    result = data / a_ice_safe
    result = result.fillna(0.0)

    result.attrs = {
        "units": "m",
        "standard_name": "surface_snow_thickness",
        "long_name": "Snow Depth",
        "processing_note": "snd = m_snow / a_ice, derived from daily m_snow and a_ice",
    }
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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

    If `extent_threshold` is set, data is first binarised (1 where data >
    threshold, 0 elsewhere) before multiplying by cell_area. This allows
    computing sea-ice extent (sum of cell areas where a_ice > 0.15) as well
    as sea-ice area (sum of a_ice * cell_area).

    Memory-efficient: masks and weights are applied via indexing (isel)
    rather than broadcasting, so only hemisphere nodes are loaded.

    Generic step — works for any variable that needs hemisphere
    integration: snow mass, ice volume, ice area, ice extent, etc.

    Rule attributes:
      - grid_file: path to mesh file (for cell_area and lat)
      - hemisphere: 'N' or 'S'
      - extent_threshold: float, optional — if set, binarise data > threshold
            before integrating (default: None, i.e. use data as-is)
    """
    grid_file = rule.get("grid_file")
    hemisphere = rule.get("hemisphere", "N")
    extent_threshold = rule.get("extent_threshold", None)
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

    # Find horizontal dimension
    horizontal_dim = None
    for dim in ["nod2", "ncells", "node"]:
        if dim in data.dims:
            horizontal_dim = dim
            break
    if horizontal_dim is None:
        raise ValueError(f"Cannot identify horizontal dim. Available: {list(data.dims)}")

    # Select hemisphere nodes by index — avoids broadcasting a full mask
    if hemisphere.upper() == "N":
        hemi_idx = np.where(lat.values >= 0)[0]
    else:
        hemi_idx = np.where(lat.values < 0)[0]

    # Subset data and area to hemisphere only (halves memory)
    data_hemi = data.isel({horizontal_dim: hemi_idx})
    area_hemi = cell_area.values[hemi_idx]

    # For extent: binarise to 1 where data > threshold (e.g. a_ice > 0.15)
    if extent_threshold is not None:
        data_hemi = (data_hemi > float(extent_threshold)).astype(float)

    # Integrate: sum(data * cell_area) over hemisphere nodes
    result = (data_hemi * area_hemi).sum(dim=horizontal_dim)
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
    result.name = rule.model_variable
    return result


# ============================================================
# Generic scaling step — reusable across models and realms
# ============================================================


_EDGE_LENGTH_CACHE = {}


def _node_edge_length(grid_file):
    """Mean great-circle edge length per node (m), derived from node_node_links."""
    if grid_file in _EDGE_LENGTH_CACHE:
        return _EDGE_LENGTH_CACHE[grid_file]
    mesh = xr.open_dataset(grid_file)
    lon = np.deg2rad(mesh["lon"].values)
    lat = np.deg2rad(mesh["lat"].values)
    links_raw = mesh["node_node_links"].values  # (nlinks_max, ncells), 1-based; NaN/0 = unused
    links = np.where(np.isfinite(links_raw), links_raw, 0).astype(np.int64)
    mesh.close()
    R = 6_371_000.0
    if links.shape[0] != lon.size and links.shape[1] == lon.size:
        pass  # already (nlinks_max, ncells)
    else:
        links = links.T
    nlinks_max, ncells = links.shape
    sums = np.zeros(ncells)
    counts = np.zeros(ncells)
    for k in range(nlinks_max):
        nbr = links[k] - 1  # to 0-based; invalid → -1
        valid = nbr >= 0
        if not valid.any():
            continue
        idx = np.where(valid)[0]
        j = nbr[idx]
        dlon = lon[j] - lon[idx]
        dlat = lat[j] - lat[idx]
        a = np.sin(dlat / 2) ** 2 + np.cos(lat[idx]) * np.cos(lat[j]) * np.sin(dlon / 2) ** 2
        d = 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        sums[idx] += d
        counts[idx] += 1
    counts[counts == 0] = 1
    edge = sums / counts
    _EDGE_LENGTH_CACHE[grid_file] = edge
    return edge


_ELEM_GEOM_CACHE = {}


def _elem_geometry(grid_file):
    """Per-element characteristic length (m) and triangle node indices (0-based).

    Returns (edge_length[ntriags], triag_nodes[3, ntriags]).
    """
    if grid_file in _ELEM_GEOM_CACHE:
        return _ELEM_GEOM_CACHE[grid_file]
    mesh = xr.open_dataset(grid_file)
    lon = np.deg2rad(mesh["lon"].values)
    lat = np.deg2rad(mesh["lat"].values)
    tri_raw = mesh["triag_nodes"].values
    mesh.close()
    tri = np.where(np.isfinite(tri_raw), tri_raw, 0).astype(np.int64)
    if tri.shape[0] != 3 and tri.shape[1] == 3:
        tri = tri.T
    tri = tri - 1  # 1-based → 0-based
    R = 6_371_000.0

    # Cartesian coords of triangle vertices
    def xyz(lon_, lat_):
        return np.stack([np.cos(lat_) * np.cos(lon_), np.cos(lat_) * np.sin(lon_), np.sin(lat_)], axis=-1)

    p0 = xyz(lon[tri[0]], lat[tri[0]])
    p1 = xyz(lon[tri[1]], lat[tri[1]])
    p2 = xyz(lon[tri[2]], lat[tri[2]])
    # flat-triangle area on unit sphere scaled by R^2
    cross = np.cross(p1 - p0, p2 - p0)
    area = 0.5 * np.linalg.norm(cross, axis=-1) * R * R
    edge = np.sqrt(np.maximum(area, 0.0))
    _ELEM_GEOM_CACHE[grid_file] = (edge, tri)
    return edge, tri


def compute_heat_transport(data, rule):
    """
    Compute oceanic heat transport across cell faces in watts.

    hfx = utemp * rho_0 * cp * hnode * edge_length     [W]

    where utemp = u*T [m/s*K], scale_factor provides rho_0*cp,
    hnode is time-varying layer thickness, and edge_length is the
    mean great-circle distance to neighbor nodes (proxy for cell-face width).

    Rule attributes:
      - scale_factor: rho_0 * cp (e.g. 4095900.0)
      - grid_file: mesh file with lon/lat/node_node_links
      - hnode_path, hnode_pattern, hnode_variable: secondary input for hnode
    """
    factor = float(rule.get("scale_factor"))
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("compute_heat_transport requires 'grid_file'")
    hnode = _load_secondary_mf(rule, "hnode_path", "hnode_pattern", "hnode_variable")

    horiz_dim = next((d for d in ("elem", "nod2", "ncells") if d in data.dims), data.dims[-1])

    if horiz_dim in ("elem",) or data.sizes[horiz_dim] > 200000 and data.sizes[horiz_dim] != hnode.sizes.get("nod2", -1):
        # Element-based: utemp/vtemp live on triangles; interpolate hnode from 3 corner nodes.
        edge_arr, tri = _elem_geometry(grid_file)
        hnode_node_dim = next((d for d in hnode.dims if hnode.sizes[d] == tri.max() + 1 or d in ("nod2", "ncells")), None)
        if hnode_node_dim is None:
            raise ValueError(f"Cannot find node dim in hnode with dims {hnode.dims}")
        hnode_elem = (hnode.isel({hnode_node_dim: xr.DataArray(tri[0], dims=[horiz_dim])})
                      + hnode.isel({hnode_node_dim: xr.DataArray(tri[1], dims=[horiz_dim])})
                      + hnode.isel({hnode_node_dim: xr.DataArray(tri[2], dims=[horiz_dim])})) / 3.0
        edge = xr.DataArray(edge_arr, dims=[horiz_dim])
        result = data * factor * hnode_elem * edge
    else:
        node_dim = horiz_dim
        if node_dim not in hnode.dims:
            for d in hnode.dims:
                if hnode.sizes[d] == data.sizes[node_dim]:
                    hnode = hnode.rename({d: node_dim})
                    break
        edge_arr = _node_edge_length(grid_file)
        edge = xr.DataArray(edge_arr, dims=[node_dim])
        result = data * factor * hnode * edge
    if rule.get("vertical_sum", False):
        for vdim in ("nz1", "nz", "depth", "lev"):
            if vdim in result.dims:
                result = result.sum(dim=vdim)
                break
    result.attrs = data.attrs.copy()
    result.attrs["units"] = "W"
    result.name = data.name
    return result


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


def upsample_to_monthly(data, rule):
    """
    Upsample an annual time series to monthly by forward-filling.

    Used for prescribed GHG forcing scalars (CFC11, CFC12, CH4, N2O, etc.)
    that are provided as annual global-mean values in input4MIPs files but
    are required at monthly frequency by CMIP7.

    Each annual value is repeated for all 12 months of that year.
    """
    return data.resample(time="MS").ffill()


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
    elif "depth_lev" in mesh:
        bottom_idx = mesh["depth_lev"].values.astype(int) - 2
    else:
        mesh.close()
        raise ValueError("Mesh file must contain 'nlevels_nod2D', 'nlevels', or 'depth_lev'")
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


def compute_msftbarot(data, rule):
    """
    Compute ocean barotropic mass streamfunction from SSH.

    Geostrophic approximation for Boussinesq free-surface models:

        psi = rho_0 * g * H / f * eta

    where:
      - eta is sea surface height (SSH, in m)
      - H   is ocean floor depth (bathymetry, in m, positive downward)
      - f   = 2*Omega*sin(lat) is the Coriolis parameter (1/s)
      - rho_0 is reference seawater density (kg/m3)
      - g   is gravitational acceleration (m/s2)

    Derivation: geostrophic balance gives depth-integrated meridional
    transport M_y = rho_0*g*H/f * d(eta)/dx. Integrating M_y = d(psi)/dx
    from the eastern boundary (psi=0) yields psi = rho_0*g*H/f * eta.

    Near the equator where |f| < f_min the result is set to NaN.
    See CMIP7 OMDP document for details on streamfunction approximations
    for free-surface ocean models.

    Primary input (data) is SSH (sea surface height, in metres).

    Rule attributes:
      - grid_file: path to mesh NetCDF file (must contain 'depth'+'depth_lev'
        or 'zbar_n_bottom', and 'lat' or 'latitude')
      - reference_density: Boussinesq rho_0 (default 1025.0 kg/m3)
      - gravity: g (default 9.80665 m/s2)
      - omega: Earth's angular velocity (default 7.2921e-5 rad/s)
      - f_min: minimum |f| cutoff for equatorial masking (default 1e-5 1/s)
    """
    rho_0 = float(rule.get("reference_density", 1025.0))
    g = float(rule.get("gravity", 9.80665))
    omega = float(rule.get("omega", 7.2921e-5))
    f_min = float(rule.get("f_min", 1e-5))

    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for compute_msftbarot step")

    mesh = xr.open_dataset(grid_file)

    # --- Ocean floor depth H (positive downward) ---
    if "depth_lev" in mesh and "depth" in mesh:
        depth_vals = mesh["depth"].values
        depth_lev = mesh["depth_lev"].values
        H = np.array(
            [
                depth_vals[min(int(nl) - 1, len(depth_vals) - 1)] if nl > 0 else 0.0
                for nl in depth_lev
            ]
        )
    elif "zbar_n_bottom" in mesh:
        H = np.abs(mesh["zbar_n_bottom"].values)
    else:
        mesh.close()
        raise ValueError("Mesh file must contain 'depth'+'depth_lev' or 'zbar_n_bottom'")

    # --- Latitude for Coriolis ---
    if "lat" in mesh:
        lat = mesh["lat"].values
    elif "latitude" in mesh:
        lat = mesh["latitude"].values
    else:
        mesh.close()
        raise ValueError("Mesh file must contain 'lat' or 'latitude'")

    mesh.close()

    # --- Horizontal dimension ---
    horizontal_dim = None
    for dim in ["nod2", "ncells", "node"]:
        if dim in data.dims:
            horizontal_dim = dim
            break
    if horizontal_dim is None:
        raise ValueError(f"Cannot identify horizontal dimension in {list(data.dims)}")

    # --- Coriolis: f = 2*Omega*sin(lat) ---
    f = 2.0 * omega * np.sin(np.deg2rad(lat))
    f_da = xr.DataArray(f, dims=[horizontal_dim])
    H_da = xr.DataArray(H, dims=[horizontal_dim])

    # --- Geostrophic streamfunction approximation ---
    # Mask equatorial singularity before dividing
    f_safe = xr.where(np.abs(f_da) >= f_min, f_da, np.nan)

    psi = rho_0 * g * H_da / f_safe * data

    psi.attrs = {
        "units": "kg s-1",
        "standard_name": "ocean_barotropic_mass_streamfunction",
        "long_name": "Ocean Barotropic Mass Streamfunction",
        "processing_note": (
            f"Geostrophic SSH approx: psi = rho_0*g*H/f*eta. "
            f"rho_0={rho_0} kg/m3, g={g} m/s2, omega={omega} rad/s, "
            f"f_min={f_min} 1/s (NaN in equatorial band |lat| < ~4 deg)."
        ),
    }
    # Keep original model_variable name; set_variable_attrs will rename to cmor_variable
    psi.name = rule.model_variable
    return psi


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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    elif nz_data == len(dz) + 1:
        # Data is on W-levels (interfaces), e.g. w with nz=48 vs 47 cell centers.
        # Average from interfaces to cell centers before multiplying by dz.
        logger.info(
            f"W-level data detected ({nz_data} levels vs {len(dz)} layers). "
            f"Averaging interfaces to cell centers."
        )
        upper = data.isel({vertical_dim: slice(None, -1)})
        lower = data.isel({vertical_dim: slice(1, None)})
        # Align by dropping the vertical coordinate so broadcasting works
        lower = lower.assign_coords({vertical_dim: upper[vertical_dim].values})
        data = 0.5 * (upper + lower)
        nz_data = len(dz)
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


def compute_salt_transport(data, rule):
    """
    Compute 3D ocean salt mass transport from velocity and salinity.

    sfx = u * S * rho_0 * dz  (x-component, from unod + salt)
    sfy = v * S * rho_0 * dz  (y-component, from vnod + salt)

    Salt (S) from FESOM is in psu (g/kg); converted to kg/kg by * 1e-3.
    Result is transport per grid-cell vertical face [kg s-1] on the native
    unstructured grid, following the same Boussinesq approximation as
    compute_mass_transport.

    Rule attributes:
      - grid_file: path to mesh file (for depth_bnds)
      - salt_path: directory containing salt files
      - salt_pattern: glob pattern for salt files (e.g. salt.fesom.*.nc)
      - salt_variable: variable name in salt files (default: 'salt')
      - reference_density: Boussinesq rho_0 (default 1025.0 kg/m3)
      - transport_component: 'x' or 'y' (for metadata only)
    """
    rho_0 = float(rule.get("reference_density", 1025.0))
    grid_file = rule.get("grid_file")

    if not isinstance(data, xr.DataArray):
        raise ValueError("compute_salt_transport expects velocity as xr.DataArray")

    # Load layer thickness from mesh
    mesh = xr.open_dataset(grid_file)
    if "depth_bnds" not in mesh:
        raise ValueError("Mesh file must contain 'depth_bnds' for layer thickness")
    dz = np.diff(mesh["depth_bnds"].values)
    mesh.close()

    # Detect vertical dimension
    vertical_dim = None
    for dim in ["nz1", "nz", "depth", "lev"]:
        if dim in data.dims:
            vertical_dim = dim
            break
    if vertical_dim is None:
        raise ValueError(f"No vertical dimension found in data. Dims: {list(data.dims)}")

    nz_data = data.sizes[vertical_dim]
    if len(dz) >= nz_data:
        thickness = xr.DataArray(dz[:nz_data], dims=[vertical_dim])
    else:
        raise ValueError(f"Mesh has {len(dz)} levels but data has {nz_data}")

    # Load salinity as secondary field
    salt = _load_secondary_mf(rule, "salt_path", "salt_pattern", "salt_variable")

    # Align time axis if needed (salt may have different time resolution)
    if "time" in data.dims and "time" in salt.dims:
        if len(salt.time) == len(data.time):
            salt = salt.assign_coords(time=data.time)
        else:
            salt = salt.reindex(time=data.time, method="ffill")

    # Convert psu → kg/kg, then compute transport
    # sfx [kg s-1 per cell face] = u [m/s] * S [kg/kg] * rho_0 [kg/m3] * dz [m]
    salt_kgkg = salt * 1e-3
    transport = data * salt_kgkg * rho_0 * thickness

    component = rule.get("transport_component", "")
    transport.name = data.name
    transport.attrs = {
        "units": "kg s-1",
        "processing_note": (
            f"Computed as velocity * (salt*1e-3) * rho_0({rho_0}) * dz. "
            f"Salt transport per grid-cell {component}-face."
        ),
    }
    return transport


def compute_salt_transport_integrated(data, rule):
    """
    Compute 2D vertically integrated ocean salt mass transport.

    sfx_int = sum_z( u * S * rho_0 * dz )  (x-component)
    sfy_int = sum_z( v * S * rho_0 * dz )  (y-component)

    Calls compute_salt_transport to get the 3D field, then sums over the
    vertical dimension to produce a 2D (lat/lon or unstructured node) field.

    Rule attributes: same as compute_salt_transport.
    """
    transport_3d = compute_salt_transport(data, rule)

    # Detect vertical dimension on the result
    vertical_dim = None
    for dim in ["nz1", "nz", "depth", "lev"]:
        if dim in transport_3d.dims:
            vertical_dim = dim
            break
    if vertical_dim is None:
        raise ValueError(f"No vertical dimension on transport field. Dims: {list(transport_3d.dims)}")

    transport_2d = transport_3d.sum(dim=vertical_dim)
    transport_2d.name = transport_3d.name
    component = rule.get("transport_component", "")
    transport_2d.attrs = {
        "units": "kg s-1",
        "processing_note": (
            f"Vertically integrated salt transport (sum over depth). "
            f"Component: {component}."
        ),
    }
    return transport_2d


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

    # Keep the model_variable name so set_variable can find and rename it
    zostoga.name = rule.model_variable
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
    result.name = rule.model_variable
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

    node_dim = "nod2" if "nod2" in data.dims else ("ncells" if "ncells" in data.dims else data.dims[-1])
    if cell_area.ndim == 1 and cell_area.dims[0] != node_dim:
        cell_area = cell_area.rename({cell_area.dims[0]: node_dim})

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
    ds = xr.open_mfdataset(files, use_cftime=True)
    time_dimname = rule.get("time_dimname")
    if time_dimname and time_dimname in ds.dims and "time" not in ds.dims:
        ds = ds.rename({time_dimname: "time"})
    # Drop residual XIOS time variables that conflict with renamed 'time'
    for _drop_var in ["time_counter", "time_centered", "time_counter_bounds", "time_centered_bounds"]:
        if _drop_var in ds.coords and _drop_var != "time":
            ds = ds.drop_vars(_drop_var, errors="ignore")
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
    return result


def compute_hur_ml(data, rule):
    """
    Compute relative humidity on model levels from ta, hus, pfull.

    OpenIFS on native model levels does not fill the `r` field (FullPos only
    emits `r` on pressure levels), so we reconstruct it from temperature,
    specific humidity and pressure using the Magnus/Tetens formula for
    saturation vapour pressure over water:

      e_sat(T) = 611.2 * exp(17.67 * (T - 273.15) / (T - 29.65))   [Pa]

    Vapour pressure from specific humidity:

      e = q * p / (0.622 + 0.378 * q)                              [Pa]

    Relative humidity:

      RH = 100 * e / e_sat

    Primary input (data) is ta (air temperature on model levels, K).
    Specific humidity and pressure are loaded from rule attributes.

    Rule attributes:
      - second_input_path: directory containing hus files
      - second_input_pattern: glob pattern for hus files
      - second_variable: variable name in hus files (e.g. "hus")
      - third_input_path: directory containing pfull files
      - third_input_pattern: glob pattern for pfull files
      - third_variable: variable name in pfull files (e.g. "pfull")
    """
    hus = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")
    pfull = _load_secondary_mf(rule, "third_input_path", "third_input_pattern", "third_variable")

    # Saturation vapour pressure over water (Bolton 1980 / Magnus form)
    e_sat = 611.2 * np.exp(17.67 * (data - 273.15) / (data - 29.65))

    # Actual vapour pressure from specific humidity and pressure
    e = hus * pfull / (0.622 + 0.378 * hus)

    result = 100.0 * e / e_sat
    result = result.clip(0, 100)

    result.attrs = {
        "units": "%",
        "standard_name": "relative_humidity",
        "long_name": "Relative Humidity",
    }
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
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
    result.name = rule.model_variable
    return result


# ============================================================
# LPJ-GUESS fire emission steps
# ============================================================

# Andreae (2019) Table 1 — savanna/grassland emission factors [g species / kg DM]
# Carbon fraction of dry matter = 0.45
_FIRE_EMISSION_FACTORS_G_PER_KG_DM = {
    "bc": 0.37,
    "ch4": 1.94,
    "co": 63.0,
    "dms": 0.68,
    "oa": 2.62,
    "so2": 0.48,
    "nmvoc": 3.4,
}
_CARBON_FRACTION = 0.45  # kg C per kg dry matter


def load_lpjguess_monthly(data, rule):
    """
    Load LPJ-GUESS monthly .out files into an xarray Dataset.

    Replaces load_mfdataset for LPJ-GUESS plain-text output. Reads all
    period directories matching the input pattern, parses the
    whitespace-delimited Lon/Lat/Year/Jan..Dec format, and returns an
    xarray Dataset with dimensions (time, ncells).

    Expects rule.inputs[0].path to point to the lpj_guess outdata directory.
    The files are at {path}/{period}/run1/<filename>.out.
    """
    import cftime
    import pandas as pd

    input_collection = rule.inputs[0]
    base_path = input_collection.path
    pattern_str = input_collection.pattern_str

    # Glob for all matching files across period subdirectories
    files = sorted(base_path.glob(pattern_str))
    if not files:
        raise FileNotFoundError(f"No LPJ-GUESS files found matching {base_path}/{pattern_str}")
    logger.info(f"Loading {len(files)} LPJ-GUESS .out files from {base_path}")

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    frames = []
    for f in files:
        logger.info(f"  * {f}")
        df = pd.read_csv(f, delim_whitespace=True)
        frames.append(df)

    df_all = pd.concat(frames, ignore_index=True)

    # Detect PFT-breakdown format: has 'Mth' column instead of Jan..Dec.
    # Sum all non-coordinate columns to produce a per-cell/per-month total.
    is_pft_format = "Mth" in df_all.columns and "Jan" not in df_all.columns
    if is_pft_format:
        coord_cols = {"Lon", "Lat", "Year", "Mth"}
        pft_cols = [c for c in df_all.columns if c not in coord_cols]
        df_all["_total"] = df_all[pft_cols].sum(axis=1)

    # Get sorted unique years
    years = np.sort(df_all["Year"].unique())

    # Build a cell index from (lon, lat) pairs, preserving the grid order
    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True])
    coords_df = coords_df.reset_index(drop=True)
    ncells = len(coords_df)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values

    # Map each (lon, lat) to a cell index
    cell_map = {(row.Lon, row.Lat): i for i, row in coords_df.iterrows()}

    # Build time coordinate
    times = []
    for yr in years:
        for m in range(1, 13):
            times.append(cftime.DatetimeProlepticGregorian(int(yr), m, 15))

    # Allocate output array
    n_times = len(times)
    values = np.full((n_times, ncells), np.nan, dtype=np.float64)

    # Fill values — Jan..Dec columns ARE the monthly data for all LPJ-GUESS .out files
    model_variable = rule.get("model_variable", "Total")
    if is_pft_format:
        for _, row in df_all.iterrows():
            cell_idx = cell_map.get((row["Lon"], row["Lat"]))
            if cell_idx is None:
                continue
            yr_idx = np.searchsorted(years, row["Year"])
            t_idx = yr_idx * 12 + (int(row["Mth"]) - 1)
            values[t_idx, cell_idx] = row["_total"]
    else:
        for _, row in df_all.iterrows():
            cell_idx = cell_map.get((row["Lon"], row["Lat"]))
            if cell_idx is None:
                continue
            yr_idx = np.searchsorted(years, row["Year"])
            for m_idx, month in enumerate(months):
                t_idx = yr_idx * 12 + m_idx
                values[t_idx, cell_idx] = row[month]

    # Create xarray Dataset
    da = xr.DataArray(
        values,
        dims=["time", "ncells"],
        coords={
            "time": times,
            "lon": ("ncells", lon_vals),
            "lat": ("ncells", lat_vals),
        },
        name=model_variable,
    )
    da.attrs["units"] = rule.get("source_units", "kg m-2 s-1")

    ds = da.to_dataset()
    return ds


def compute_fire_emission(data, rule):
    """
    Convert total fire carbon flux to species-specific emission flux.

    Reads rule.emission_species to select the emission factor from
    Andreae (2019) Table 1 (savanna/grassland). Converts from
    kg C m-2 s-1 to kg species m-2 s-1.

    Conversion: flux_species = flux_C * EF / (C_frac * 1000)
      where EF is in g/kgDM and C_frac = 0.45 kgC/kgDM.
    """
    species = rule.get("emission_species")
    if species is None:
        raise ValueError("Rule must specify 'emission_species' for compute_fire_emission")

    ef = _FIRE_EMISSION_FACTORS_G_PER_KG_DM.get(species)
    if ef is None:
        raise ValueError(
            f"Unknown emission species '{species}'. " f"Available: {list(_FIRE_EMISSION_FACTORS_G_PER_KG_DM.keys())}"
        )

    # g/kgDM -> kg_species/kgC: divide by 1000 (g->kg) and by C_frac (kgDM->kgC)
    conversion_factor = ef / (_CARBON_FRACTION * 1000.0)

    model_variable = rule.get("model_variable", "Total")
    da = data[model_variable]

    da_species = da * conversion_factor
    da_species.attrs = da.attrs.copy()
    da_species.attrs["units"] = "kg m-2 s-1"
    da_species.name = model_variable

    ds = da_species.to_dataset()
    # Carry over coordinates
    for coord in data.coords:
        if coord not in ds.coords:
            ds.coords[coord] = data.coords[coord]

    logger.info(
        f"Applied emission factor for '{species}': "
        f"EF={ef} g/kgDM, conversion={conversion_factor:.6e} kg_species/kgC"
    )
    return ds


# ============================================================
# LPJ-GUESS loaders for yearly and Lut file formats
# ============================================================


def load_lpjguess_yearly(data, rule):
    """
    Load LPJ-GUESS yearly .out files (Lon/Lat/Year/Total format).

    Returns an xarray Dataset with dimensions (time, ncells) where time
    has one entry per year (mid-year: July 1).
    """
    import cftime
    import pandas as pd

    input_collection = rule.inputs[0]
    base_path = input_collection.path
    pattern_str = input_collection.pattern_str

    files = sorted(base_path.glob(pattern_str))
    if not files:
        raise FileNotFoundError(f"No LPJ-GUESS files found matching {base_path}/{pattern_str}")
    logger.info(f"Loading {len(files)} LPJ-GUESS yearly .out files from {base_path}")

    frames = []
    for f in files:
        logger.info(f"  * {f}")
        df = pd.read_csv(f, delim_whitespace=True)
        frames.append(df)

    df_all = pd.concat(frames, ignore_index=True)
    years = np.sort(df_all["Year"].unique())

    # Build cell index
    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True]).reset_index(drop=True)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values
    ncells = len(coords_df)
    cell_map = {(row.Lon, row.Lat): i for i, row in coords_df.iterrows()}

    # Time coordinate: one per year (mid-year)
    times = [cftime.DatetimeProlepticGregorian(int(yr), 7, 1) for yr in years]

    model_variable = rule.get("model_variable", "Total")
    values = np.full((len(times), ncells), np.nan, dtype=np.float64)

    for _, row in df_all.iterrows():
        cell_idx = cell_map.get((row["Lon"], row["Lat"]))
        if cell_idx is None:
            continue
        yr_idx = np.searchsorted(years, row["Year"])
        values[yr_idx, cell_idx] = row[model_variable]

    da = xr.DataArray(
        values,
        dims=["time", "ncells"],
        coords={"time": times, "lon": ("ncells", lon_vals), "lat": ("ncells", lat_vals)},
        name=model_variable,
    )
    source_units = rule.get("source_units")
    if source_units:
        da.attrs["units"] = source_units
    return da.to_dataset()


def load_lpjguess_yearly_lut(data, rule):
    """
    Load LPJ-GUESS yearly Lut .out files (Lon/Lat/Year/psl/crp/pst/urb format).

    Returns an xarray Dataset with dimensions (time, ncells). Reads the
    column specified by rule.model_variable (typically 'psl').
    """
    import cftime
    import pandas as pd

    input_collection = rule.inputs[0]
    base_path = input_collection.path
    pattern_str = input_collection.pattern_str

    files = sorted(base_path.glob(pattern_str))
    if not files:
        raise FileNotFoundError(f"No LPJ-GUESS files found matching {base_path}/{pattern_str}")
    logger.info(f"Loading {len(files)} LPJ-GUESS yearly Lut .out files from {base_path}")

    frames = []
    for f in files:
        logger.info(f"  * {f}")
        df = pd.read_csv(f, delim_whitespace=True)
        frames.append(df)

    df_all = pd.concat(frames, ignore_index=True)
    years = np.sort(df_all["Year"].unique())

    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True]).reset_index(drop=True)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values
    ncells = len(coords_df)
    cell_map = {(row.Lon, row.Lat): i for i, row in coords_df.iterrows()}

    times = [cftime.DatetimeProlepticGregorian(int(yr), 7, 1) for yr in years]

    model_variable = rule.get("model_variable", "psl")
    values = np.full((len(times), ncells), np.nan, dtype=np.float64)

    for _, row in df_all.iterrows():
        cell_idx = cell_map.get((row["Lon"], row["Lat"]))
        if cell_idx is None:
            continue
        yr_idx = np.searchsorted(years, row["Year"])
        values[yr_idx, cell_idx] = row[model_variable]

    da = xr.DataArray(
        values,
        dims=["time", "ncells"],
        coords={"time": times, "lon": ("ncells", lon_vals), "lat": ("ncells", lat_vals)},
        name=model_variable,
    )
    source_units = rule.get("source_units")
    if source_units:
        da.attrs["units"] = source_units
    return da.to_dataset()


def load_lpjguess_monthly_lut(data, rule):
    """
    Load LPJ-GUESS monthly Lut .out files (Lon/Lat/Year/Mth/psl/crp/pst/urb format).

    Returns an xarray Dataset with dimensions (time, ncells). Each row
    in the .out file is one (gridpoint, year, month) tuple.
    """
    import cftime
    import pandas as pd

    input_collection = rule.inputs[0]
    base_path = input_collection.path
    pattern_str = input_collection.pattern_str

    files = sorted(base_path.glob(pattern_str))
    if not files:
        raise FileNotFoundError(f"No LPJ-GUESS files found matching {base_path}/{pattern_str}")
    logger.info(f"Loading {len(files)} LPJ-GUESS monthly Lut .out files from {base_path}")

    frames = []
    for f in files:
        logger.info(f"  * {f}")
        df = pd.read_csv(f, delim_whitespace=True)
        frames.append(df)

    df_all = pd.concat(frames, ignore_index=True)
    years = np.sort(df_all["Year"].unique())

    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True]).reset_index(drop=True)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values
    ncells = len(coords_df)
    cell_map = {(row.Lon, row.Lat): i for i, row in coords_df.iterrows()}

    # Build time axis: one per (year, month)
    times = []
    for yr in years:
        for m in range(1, 13):
            times.append(cftime.DatetimeProlepticGregorian(int(yr), m, 15))

    model_variable = rule.get("model_variable", "psl")
    n_times = len(times)
    values = np.full((n_times, ncells), np.nan, dtype=np.float64)

    for _, row in df_all.iterrows():
        cell_idx = cell_map.get((row["Lon"], row["Lat"]))
        if cell_idx is None:
            continue
        yr_idx = np.searchsorted(years, row["Year"])
        m_idx = int(row["Mth"]) - 1
        t_idx = yr_idx * 12 + m_idx
        values[t_idx, cell_idx] = row[model_variable]

    da = xr.DataArray(
        values,
        dims=["time", "ncells"],
        coords={"time": times, "lon": ("ncells", lon_vals), "lat": ("ncells", lat_vals)},
        name=model_variable,
    )
    source_units = rule.get("source_units")
    if source_units:
        da.attrs["units"] = source_units
    return da.to_dataset()


# ============================================================
# IFS land custom computation steps
# ============================================================


def compute_temporal_diff(data, rule):
    """
    Compute temporal difference of a variable (for dgw, dsn, dsw).

    For dgw: diff of swvl4 * layer_thickness * 1000
    For dsn: diff of sd * scale_factor
    For dsw: diff of total water storage
    """
    model_variable = rule.get("model_variable")
    scale_factor = rule.get("scale_factor", 1.0)
    layer_thickness = rule.get("layer_thickness", 1.0)

    if model_variable == "total_water":
        # Compute total water storage: soil moisture + snow + skin reservoir
        da = (
            1000.0 * (data["swvl1"] * 0.07 + data["swvl2"] * 0.21 + data["swvl3"] * 0.72 + data["swvl4"] * 1.89)
            + data["sd"] * 1000.0
            + data["src"] * 1000.0
        )
    elif model_variable == "skin_reservoir":
        # dcw: change in canopy interception storage (src in m → kg/m2)
        da = data["src"] * 1000.0
    elif model_variable == "soil_moisture":
        # dslw: change in total soil moisture (all 4 HTESSEL layers)
        da = 1000.0 * (data["swvl1"] * 0.07 + data["swvl2"] * 0.21 + data["swvl3"] * 0.72 + data["swvl4"] * 1.89)
    else:
        da = data[model_variable] * float(layer_thickness) * 1000.0 * float(scale_factor)

    diff = da.diff(dim="time")
    diff.attrs["units"] = "kg m-2"
    diff.name = model_variable

    ds = diff.to_dataset()
    for coord in data.coords:
        if coord not in ds.coords and coord != "time":
            ds.coords[coord] = data.coords[coord]
    return ds


def compute_mrtws(data, rule):
    """
    Compute terrestrial water storage (mrtws).

    Sum of all water stores: soil moisture (4 layers) + snow + skin reservoir.
    HTESSEL layer thicknesses: 0.07, 0.21, 0.72, 1.89 m.
    """
    mrtws = (
        1000.0 * (data["swvl1"] * 0.07 + data["swvl2"] * 0.21 + data["swvl3"] * 0.72 + data["swvl4"] * 1.89)
        + data["sd"] * 1000.0
        + data["src"] * 1000.0
    )
    mrtws.attrs["units"] = "kg m-2"
    mrtws.name = rule.model_variable

    ds = mrtws.to_dataset()
    for coord in data.coords:
        if coord not in ds.coords:
            ds.coords[coord] = data.coords[coord]
    return ds


def compute_snd(data, rule):
    """
    Compute physical snow depth from SWE and snow density.

    snd = sd * 1000 / rsn  (SWE in m water equiv → physical depth in m)
    Where rsn = 0, snd = 0 (no snow).
    """
    if isinstance(data, xr.Dataset):
        sd = data["sd"]
    else:
        sd = data
    rsn = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")

    snd = xr.where(rsn > 0, sd * 1000.0 / rsn, 0.0)
    snd.attrs["units"] = "m"
    snd.name = rule.model_variable

    ds = snd.to_dataset()
    for coord in sd.coords:
        if coord not in ds.coords:
            ds.coords[coord] = sd.coords[coord]
    return ds


def sum_lpjguess_monthly_files(data, rule):
    """
    Load and sum multiple LPJ-GUESS monthly .out files.

    For variables like c3PftFrac that are the sum of multiple output files
    (grassFracC3 + treeFracBdlDcd + treeFracBdlEvg + treeFracNdlDcd + treeFracNdlEvg).

    Primary input (data) is already loaded (first file).
    Rule attributes:
      - additional_files: comma-separated list of additional .out filenames
        e.g. "treeFracBdlDcd_monthly.out,treeFracBdlEvg_monthly.out,..."
      - lpjg_data_path: base path to LPJ-GUESS output
      - additional_pattern_prefix: glob prefix for period dirs (default: "*/run1/")
    """
    lpjg_path = rule.get("lpjg_data_path")
    additional = rule.get("additional_files", "")
    prefix = rule.get("additional_pattern_prefix", "*/run1/")

    if not additional or not lpjg_path:
        return data

    # data is an xr.Dataset from load_lpjguess_monthly; extract the single variable
    var_names = [v for v in data.data_vars if v not in data.coords]
    result = data[var_names[0]]

    import cftime
    import pandas as pd

    for filename in additional.split(","):
        filename = filename.strip()
        if not filename:
            continue
        file_pattern = _os.path.join(lpjg_path, prefix, filename)
        files = sorted(_glob.glob(file_pattern))
        if not files:
            logger.warning(f"No files matching {file_pattern}, skipping")
            continue
        # Read with the same logic as load_lpjguess_monthly
        frames = []
        for f in files:
            df = pd.read_csv(f, sep=r"\s+")
            frames.append(df)
        df_all = pd.concat(frames, ignore_index=True)
        years = sorted(df_all["Year"].unique())
        month_cols = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        time_vals = []
        data_list = []
        for yr in years:
            yr_df = df_all[df_all["Year"] == yr].sort_values(["Lat", "Lon"], ascending=[False, True])
            for mi, mcol in enumerate(month_cols):
                time_vals.append(cftime.DatetimeProlepticGregorian(int(yr), mi + 1, 15))
                data_list.append(yr_df[mcol].values)
        arr = np.array(data_list)
        da = xr.DataArray(
            arr,
            dims=["time", "ncells"],
            coords={"time": time_vals},
        )
        result = result + da

    out_name = rule.get("output_variable", var_names[0])
    result.attrs = data[var_names[0]].attrs.copy()
    result.name = out_name
    ds_out = result.to_dataset()
    for coord in data.coords:
        if coord not in ds_out.coords:
            ds_out.coords[coord] = data.coords[coord]
    return ds_out


def compute_mrsow(data, rule):
    """
    Compute total soil wetness as fraction of saturation.

    mrsow = (swvl1*d1 + swvl2*d2 + swvl3*d3 + swvl4*d4) /
            (porosity * (d1 + d2 + d3 + d4))

    HTESSEL layer thicknesses: d1=0.07, d2=0.21, d3=0.72, d4=1.89 m.
    HTESSEL porosity varies by soil type but a representative global
    average is ~0.472 (loam).

    Rule attributes:
      - porosity: soil porosity (default: 0.472, HTESSEL loam)
    """
    porosity = float(rule.get("porosity", 0.472))
    d1, d2, d3, d4 = 0.07, 0.21, 0.72, 1.89
    total_depth = d1 + d2 + d3 + d4

    # Weighted average volumetric soil moisture
    swvl_avg = (data["swvl1"] * d1 + data["swvl2"] * d2 + data["swvl3"] * d3 + data["swvl4"] * d4) / total_depth

    result = swvl_avg / porosity
    # Clip to [0, 1]
    result = result.clip(0.0, 1.0)
    result.attrs = {"units": "1", "long_name": "Total Soil Wetness"}
    result.name = rule.model_variable

    ds = result.to_dataset()
    for coord in data.coords:
        if coord not in ds.coords:
            ds.coords[coord] = data.coords[coord]
    return ds


def select_southern_hemisphere(data, rule):
    """
    Select Southern Hemisphere subset (south of 30S).

    For CMIP7 variables with region=30S-90S (e.g., orogSouth30, tasSouth30).
    Selects latitudes <= -30.
    """
    lat_name = None
    for name in ["lat", "latitude", "nav_lat"]:
        if name in data.coords:
            lat_name = name
            break
    if lat_name is None:
        raise ValueError("Cannot find latitude coordinate in data")
    result = data.sel({lat_name: data[lat_name] <= -30.0})
    return result


def compute_sftgif(data, rule):
    """
    Compute glacier fraction from IFS vegetation type fields.

    IFS vegetation type 12 = "Ice Caps and Glaciers" (BATS classification).
    sftgif = cvl * (tvl == 12) * 100 + cvh * (tvh == 12) * 100

    Input data should contain tvl, tvh, cvl, cvh fields.
    """
    tvl = data["tvl"]
    tvh = data["tvh"]
    cvl = data["cvl"]
    cvh = data["cvh"]

    # Vegetation type 12 = Ice Caps and Glaciers
    glacier = cvl * (tvl == 12).astype(float) + cvh * (tvh == 12).astype(float)
    result = glacier * 100.0  # fraction → percent

    result.attrs = {"units": "%", "long_name": "Fraction of Grid Cell Covered with Glacier"}
    result.name = rule.model_variable

    ds = result.to_dataset()
    for coord in data.coords:
        if coord not in ds.coords:
            ds.coords[coord] = data.coords[coord]
    return ds


# HTESSEL field capacity lookup table (Van Genuchten parameters per soil type)
# Soil types 1-7 from IFS documentation, field capacity as volumetric fraction
# Source: HTESSEL sussoil_mod.F90, Van Genuchten parameters → theta at pF=2.5
_HTESSEL_FIELD_CAPACITY = {
    1: 0.242,  # Coarse (sand)
    2: 0.346,  # Medium (loam)
    3: 0.382,  # Medium fine (clay loam)
    4: 0.448,  # Fine (clay)
    5: 0.310,  # Very fine (silty clay)
    6: 0.370,  # Organic
    7: 0.420,  # Tropical organic
}


def compute_mrsofc(data, rule):
    """
    Compute soil field capacity from IFS soil type.

    HTESSEL has 7 soil types with known Van Genuchten parameters.
    Field capacity (theta at pF=2.5) is looked up per soil type,
    then integrated over the full soil column (2.89 m).

    mrsofc = theta_fc * total_depth * rho_water
           = theta_fc * 2.89 * 1000 (kg m-2)

    Input data should contain 'slt' (soil type, integer 1-7).
    """
    slt = data["slt"]
    total_depth = 0.07 + 0.21 + 0.72 + 1.89  # 2.89 m

    # Map soil type to field capacity
    theta_fc = xr.zeros_like(slt, dtype=float)
    for stype, fc in _HTESSEL_FIELD_CAPACITY.items():
        theta_fc = xr.where(np.round(slt) == stype, fc, theta_fc)

    result = theta_fc * total_depth * 1000.0  # m3/m3 * m * kg/m3 → kg/m2

    result.attrs = {
        "units": "kg m-2",
        "long_name": "Soil Moisture at Field Capacity",
    }
    result.name = rule.model_variable

    ds = result.to_dataset()
    for coord in data.coords:
        if coord not in ds.coords:
            ds.coords[coord] = data.coords[coord]
    return ds


# HTESSEL root depth by vegetation type (Zeng et al. 1998 effective depth)
# IFS BATS vegetation types with 95% cumulative root fraction depth (m)
_HTESSEL_ROOT_DEPTH = {
    1: 1.00,  # Crops, mixed farming
    2: 1.00,  # Short grass
    3: 1.50,  # Evergreen needleleaf
    4: 1.50,  # Deciduous needleleaf
    5: 1.50,  # Deciduous broadleaf
    6: 2.00,  # Evergreen broadleaf
    7: 1.00,  # Tall grass
    8: 0.50,  # Desert
    9: 0.50,  # Tundra
    10: 1.00,  # Irrigated crops
    11: 0.50,  # Semidesert
    12: 0.00,  # Ice caps and glaciers
    13: 0.50,  # Bogs and marshes
    14: 0.00,  # Inland water
    15: 0.00,  # Ocean
    16: 1.50,  # Evergreen shrubs
    17: 1.00,  # Deciduous shrubs
    18: 1.50,  # Mixed forest
    19: 1.00,  # Interrupted forest
    20: 0.00,  # Water and land mix
}


def compute_rootd(data, rule):
    """
    Compute effective maximum root depth from IFS vegetation types.

    Uses vegetation-type-weighted root depth:
    rootd = cvl * rootd(tvl) + cvh * rootd(tvh)

    Input data should contain tvl, tvh, cvl, cvh fields.
    """
    tvl = data["tvl"]
    tvh = data["tvh"]
    cvl = data["cvl"]
    cvh = data["cvh"]

    rootd_low = xr.zeros_like(tvl, dtype=float)
    rootd_high = xr.zeros_like(tvh, dtype=float)

    for vtype, depth in _HTESSEL_ROOT_DEPTH.items():
        rootd_low = xr.where(np.round(tvl) == vtype, depth, rootd_low)
        rootd_high = xr.where(np.round(tvh) == vtype, depth, rootd_high)

    result = cvl * rootd_low + cvh * rootd_high

    result.attrs = {"units": "m", "long_name": "Maximum Root Depth"}
    result.name = rule.model_variable

    ds = result.to_dataset()
    for coord in data.coords:
        if coord not in ds.coords:
            ds.coords[coord] = data.coords[coord]
    return ds


# ============================================================
# CAP7 atmosphere steps
# ============================================================


def compute_rtmt(data, rule):
    """
    Compute net downward radiative flux at top of model.

    rtmt = rsdt - rsut + rlds - rlus

    Primary input (data) should be a Dataset containing rsdt, rsut,
    rlds, and rlus from the _day_cap7 or monthly XIOS output.
    """
    rsdt = data["rsdt"]
    rsut = data["rsut"]
    rlds = data["rlds"]
    rlus = data["rlus"]

    result = (rsdt - rsut) + (rlds - rlus)
    result.attrs = {
        "units": "W m-2",
        "standard_name": "net_downward_radiative_flux_at_top_of_atmosphere_model",
        "long_name": "Net Downward Radiative Flux at Top of Model",
    }
    result.name = rule.model_variable
    return result.to_dataset()


def regrid_regular_to_fesom(data, rule):
    """
    Interpolate data from a regular lat/lon grid onto FESOM unstructured nodes.

    Reads FESOM node coordinates from rule.grid_file and uses bilinear
    interpolation (scipy RegularGridInterpolator) to map each timestep.

    Rule attributes:
      - grid_file: path to FESOM mesh.nc (required, contains 'lon'/'lat' node coords)
      - fesom_node_dim: name of node dimension in output (default: 'nod2')
    """
    from scipy.interpolate import RegularGridInterpolator

    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for regrid_regular_to_fesom")

    node_dim = rule.get("fesom_node_dim", "nod2")

    # Read FESOM node coordinates from mesh.nc
    mesh = xr.open_dataset(grid_file)
    fesom_lon = None
    fesom_lat = None
    for name in ["lon", "longitude"]:
        if name in mesh:
            fesom_lon = mesh[name].values
            break
    for name in ["lat", "latitude"]:
        if name in mesh:
            fesom_lat = mesh[name].values
            break
    mesh.close()
    if fesom_lon is None or fesom_lat is None:
        raise ValueError(f"Cannot find lon/lat in grid_file: {grid_file}")

    # Identify source grid coordinate names and dims
    src_lat = src_lon = src_lat_dim = src_lon_dim = None
    for name in ["lat", "latitude"]:
        if name in data.coords:
            src_lat = data.coords[name].values
            src_lat_dim = name
            break
    for name in ["lon", "longitude"]:
        if name in data.coords:
            src_lon = data.coords[name].values
            src_lon_dim = name
            break
    if src_lat is None or src_lon is None:
        raise ValueError(f"Cannot find lat/lon coords in data. Available: {list(data.coords)}")

    # Normalise FESOM lons to match the source grid range
    if src_lon.max() > 180:
        # source is 0..360
        fesom_lon_q = fesom_lon % 360.0
    else:
        # source is -180..180
        fesom_lon_q = ((fesom_lon + 180.0) % 360.0) - 180.0

    query_pts = np.column_stack([fesom_lat, fesom_lon_q])

    def _interp_timestep(arr2d):
        interp = RegularGridInterpolator(
            (src_lat, src_lon), arr2d,
            method="linear", bounds_error=False, fill_value=np.nan,
        )
        return interp(query_pts).astype(np.float32)

    # Apply interpolation over time
    time_dim = "time"
    if time_dim not in data.dims:
        result_np = _interp_timestep(data.values)
        result = xr.DataArray(result_np, dims=[node_dim], attrs=data.attrs)
    else:
        slices = [_interp_timestep(data.isel({time_dim: t}).values)
                  for t in range(len(data[time_dim]))]
        result = xr.DataArray(
            np.array(slices),
            dims=[time_dim, node_dim],
            coords={time_dim: data[time_dim]},
            attrs=data.attrs,
        )

    result.name = data.name
    return result


def mask_where_no_seaice(data, rule):
    """
    Mask data to NaN wherever there is no sea ice (a_ice == 0).

    Loads FESOM sea ice concentration from rule.aice_file and sets data values
    to NaN at all FESOM nodes where a_ice is zero, matching by time coordinate.

    Rule attributes:
      - aice_file: path (or glob pattern) to FESOM a_ice file(s), e.g.
          /path/to/outdata/fesom/a_ice.fesom.*.nc  (required)
      - fesom_node_dim: name of node dimension (default: 'nod2')
    """
    import glob as _glob

    aice_file = rule.get("aice_file")
    if aice_file is None:
        raise ValueError("Rule must specify 'aice_file' for mask_where_no_seaice")

    node_dim = rule.get("fesom_node_dim", "nod2")

    # Support glob patterns
    paths = sorted(_glob.glob(aice_file))
    if not paths:
        raise FileNotFoundError(f"No files matched aice_file pattern: {aice_file}")

    a_ice = xr.open_mfdataset(paths, combine="by_coords")["a_ice"]

    # Align time coordinates: match data times to a_ice times
    # Both should be on monthly cadence; use sel with tolerance
    time_dim = "time"
    if time_dim in data.dims and time_dim in a_ice.dims:
        a_ice = a_ice.sel({time_dim: data[time_dim]}, method="nearest")

    # Mask: set to NaN where a_ice == 0 (no sea ice)
    mask = a_ice > 0  # True where sea ice present
    if hasattr(data, "name"):
        result = data.where(mask)
        result.name = data.name
    else:
        result = data.where(mask)

    return result


def extract_single_plevel(data, rule):
    """
    Extract a single pressure level from a multi-level dataset.

    Rule attributes:
      - model_variable: variable name in dataset (e.g. 't', 'w')
      - target_plevel: pressure level in Pa (e.g. 70000 for 700 hPa, 50000 for 500 hPa)
    """
    var = rule.model_variable
    plevel = float(rule.target_plevel)

    import xarray as xr
    da = data if isinstance(data, xr.DataArray) else data[var]
    # Find the pressure level dimension
    plev_dim = None
    for dim in da.dims:
        if "lev" in dim or "plev" in dim or "pressure" in dim:
            plev_dim = dim
            break
    if plev_dim is None:
        raise ValueError(f"Cannot find pressure level dimension in {da.dims}")

    result = da.sel({plev_dim: plevel}, method="nearest")
    result = result.drop_vars(plev_dim, errors="ignore")
    return result.to_dataset()


# ============================================================
# Basin-latitude binned diagnostics (msftmz, hfbasin, sltbasin)
# Algorithms adapted from tripyview (calc_zmoc, calc_mhflx_box_fast)
# and pyfesom2 (xmoc_data). No external dependencies required.
# ============================================================


_BASIN_IDS = (1, 2, 3, 10, 11)  # Atl, Pac, Ind, Arctic, SO — matches basin_mask.nc
_BASIN_NAMES = ("atlantic", "pacific", "indian", "arctic", "southern")
# CMIP basin axis (CMIP6_coordinate.json → 'basin') requires exactly three names.
_CMIP_BASIN_NAMES = ("atlantic_arctic_ocean", "indian_pacific_ocean", "global_ocean")
_CMIP_BASIN_AGG = {
    "atlantic_arctic_ocean": (0, 3),           # atlantic + arctic
    "indian_pacific_ocean":  (1, 2),           # pacific + indian
    "global_ocean":          (0, 1, 2, 3, 4),  # all
}
# Subdivided basins are only meaningful north of this; south of it only global_ocean
# is reported. CMIP convention ~34°S.
_BASIN_SOUTH_CUTOFF = -34.0


def _aggregate_to_cmip_basins(binned, lat_centers, cutoff=_BASIN_SOUTH_CUTOFF):
    """Collapse 5-basin intermediate → 3 CMIP basins.

    binned: array shape (..., 5, nlat) ordered per _BASIN_NAMES.
    Returns array shape (..., 3, nlat) ordered per _CMIP_BASIN_NAMES.
    atlantic_arctic & indian_pacific → NaN south of cutoff; global_ocean untouched.
    """
    south = np.asarray(lat_centers) < cutoff
    out_shape = binned.shape[:-2] + (3, binned.shape[-1])
    out = np.zeros(out_shape, dtype=np.float64)
    for j, name in enumerate(_CMIP_BASIN_NAMES):
        idxs = list(_CMIP_BASIN_AGG[name])
        out[..., j, :] = binned[..., idxs, :].sum(axis=-2)
        if name != "global_ocean":
            out[..., j, south] = np.nan
    return out
_RHO0 = 1030.0
_CP = 3900.0


def _load_basin_nodes(rule):
    """Return node→basin-id array from rule.basin_mask_file (rename ncells→nod2)."""
    path = rule.get("basin_mask_file")
    if path is None:
        raise ValueError("Rule must specify 'basin_mask_file'")
    ds = xr.open_dataset(path)
    b = ds["basin"].values
    ds.close()
    return b


def _mesh_nodes(grid_file):
    """Return (lat_nodes, cell_area, depth_bnds, tri) from FESOM mesh.nc.

    tri is int64 (3, ntriags), 0-based.
    """
    m = xr.open_dataset(grid_file)
    lat = m["lat"].values
    area = m["cell_area"].values
    dbnds = m["depth_bnds"].values
    tri_raw = m["triag_nodes"].values
    m.close()
    tri = np.where(np.isfinite(tri_raw), tri_raw, 0).astype(np.int64)
    if tri.shape[0] != 3 and tri.shape[1] == 3:
        tri = tri.T
    tri = tri - 1
    return lat, area, dbnds, tri


def _elem_lat_area(lat_nodes, cell_area, tri):
    """Per-element latitude (triangle centroid), horizontal area (m²), and
    zonal width dx = area / dy_elem where dy_elem is the triangle's meridional extent (m)."""
    elem_lat = lat_nodes[tri].mean(axis=0)
    elem_area = (cell_area[tri[0]] + cell_area[tri[1]] + cell_area[tri[2]]) / 3.0
    lat_min = lat_nodes[tri].min(axis=0)
    lat_max = lat_nodes[tri].max(axis=0)
    dy_elem_m = np.maximum(np.deg2rad(lat_max - lat_min) * 6_371_000.0, 1.0)
    elem_dx = elem_area / dy_elem_m  # effective zonal width (m)
    return elem_lat, elem_area, elem_dx


def _lat_edges(dlat=1.0):
    return np.arange(-90.0, 90.0 + dlat / 2, dlat)


def _basin_lat_crossing_sum(values, min_lat, max_lat, loc_basin, lat_centers, basin_ids=_BASIN_IDS):
    """Sum values over (basin, lat_bin) for elements whose [min_lat, max_lat]
    contains lat_centers[j]. Vectorized via interval-scatter + cumsum.
    values shape (..., nelem)."""
    nlat = lat_centers.size
    nb = len(basin_ids)
    lead = values.shape[:-1]
    flat_lead = int(np.prod(lead)) if lead else 1
    vals_flat = values.reshape(flat_lead, values.shape[-1])  # (L, nelem)

    # For each element, find contiguous range of lat bin indices it straddles
    lo = np.searchsorted(lat_centers, min_lat, side="left")
    hi = np.searchsorted(lat_centers, max_lat, side="right")  # exclusive
    # valid elements: lo < nlat and hi > 0 and lo < hi
    valid = (lo < nlat) & (hi > lo)

    out = np.zeros((flat_lead, nb, nlat), dtype=np.float64)
    for bi, bid in enumerate(basin_ids):
        sel = valid & (loc_basin == bid)
        if not sel.any():
            continue
        lo_s = np.clip(lo[sel], 0, nlat)
        hi_s = np.clip(hi[sel], 0, nlat)
        vs = vals_flat[:, sel]  # (L, nsel)
        # interval scatter: add vs at lo_s, subtract at hi_s; cumsum on lat axis
        delta = np.zeros((flat_lead, nlat + 1), dtype=np.float64)
        np.add.at(delta, (slice(None), lo_s), vs)
        np.add.at(delta, (slice(None), hi_s), -vs)
        out[:, bi, :] = np.cumsum(delta[:, :nlat], axis=1)
    return out.reshape(lead + (nb, nlat))


def _basin_lat_sum(values, loc_lat, loc_basin, lat_edges, basin_ids=_BASIN_IDS):
    """Sum values over (basin, lat_bin). values shape (..., nloc).

    Returns array shape (..., n_basins, n_lat_bins-1) with leading dims preserved.
    """
    nlat = lat_edges.size - 1
    nb = len(basin_ids)
    lat_idx = np.clip(np.searchsorted(lat_edges, loc_lat, side="right") - 1, 0, nlat - 1)
    lead = values.shape[:-1]
    flat_lead = int(np.prod(lead)) if lead else 1
    vals_flat = values.reshape(flat_lead, values.shape[-1])  # (L, nloc)
    out = np.zeros((flat_lead, nb, nlat), dtype=np.float64)
    for bi, bid in enumerate(basin_ids):
        sel = loc_basin == bid
        if not sel.any():
            continue
        sub_vals = vals_flat[:, sel]  # (L, nsel)
        sub_lat = lat_idx[sel]        # (nsel,)
        # accumulate column-wise into out[:, bi, sub_lat]
        # np.add.at with (row_idx, col_idx) broadcasts shapes
        rows = np.arange(flat_lead)[:, None]
        cols = sub_lat[None, :]
        np.add.at(out[:, bi, :], (rows, cols), sub_vals)
    return out.reshape(lead + (nb, nlat))


def compute_msftmz(data, rule):
    """
    Ocean meridional overturning mass streamfunction (CMIP msftmz), kg s-1.

    Wraps tripyview's calc_zmoc for the three CMIP basin options:
      atlantic_arctic_ocean → 'aamoc'
      indian_pacific_ocean  → 'ipmoc'
      global_ocean          → 'gmoc'

    Each basin call returns ψ on its own basin-specific lat grid (shapefile-based);
    here we align them onto a single 1°-dlat global latitude axis and fill missing
    lat bands with NaN (already CMIP-compliant: subdivided basins NaN south of ~34°S).

    Inputs:
      data: xr.Dataset with 'w' (time, nz, nod2) — 3D vertical velocity on nodes.
      rule.mesh_path: FESOM mesh directory (for tpv.load_mesh_fesom2).
      Optional rule.diag_file: path to fesom.mesh.diag.nc; else inferred from mesh_path.
    Output: DataArray (time, lev, basin, lat) in kg s-1 (tripyview returns Sv;
    we scale by ρ₀·10⁹ to get kg s-1).
    """
    import tripyview as tpv
    mesh_path = rule.get("mesh_path")
    if mesh_path is None:
        raise ValueError("compute_msftmz requires 'mesh_path' (FESOM mesh directory)")
    diagpath = rule.get("diag_file", f"{mesh_path}/fesom.mesh.diag.nc")

    mesh = tpv.load_mesh_fesom2(mesh_path, do_info=False)
    w = data[["w"]] if isinstance(data, xr.Dataset) else data.to_dataset()
    if "time" not in w.dims:
        w = w.expand_dims("time")
    # tripyview propagates data.chunksizes onto mesh-area arrays (dims 'nz','nod2'),
    # which fails if w has a 'time' chunk. Drop chunks by loading into memory.
    w = w.load()
    w = w.assign_coords(lat=("nod2", mesh.n_y), lon=("nod2", mesh.n_x))

    # Align w's vertical dim to whatever tripyview's nod_area uses. tripyview
    # renames nl->nz and nl1->nz1 in the diag file's 'nod_area'; if the diag
    # file stores nod_area on half-levels (nl1), the product w*nod_area ends
    # up with both 'nz' (from w) and 'nz1' (from nod_area), which breaks the
    # final transpose to ('time','nz1','lat'). Detect the diag vertical dim
    # and rename w's vertical dim to match so only one vertical dim survives.
    try:
        import os as _os
        if _os.path.isfile(diagpath):
            with xr.open_dataset(diagpath) as _diag:
                _na_dims = set(_diag["nod_area"].dims)
            _diag_vdim = None
            for _src, _dst in (("nl", "nz"), ("nl1", "nz1"), ("nz", "nz"), ("nz1", "nz1")):
                if _src in _na_dims:
                    _diag_vdim = _dst
                    break
            if _diag_vdim is not None:
                # w typically has 'nz'; rename to the diag file's vertical dim
                for _wv in ("nz", "nz1"):
                    if _wv in w.dims and _wv != _diag_vdim:
                        w = w.rename({_wv: _diag_vdim})
                        break
    except Exception:
        # Best-effort alignment; fall through and let tripyview raise if needed.
        pass

    basin_to_key = {
        "atlantic_arctic_ocean": "aamoc",
        "indian_pacific_ocean":  "ipmoc",
        "global_ocean":          "gmoc",
    }

    # Global 1° lat grid matching tripyview's integer-lat convention
    dlat = 1.0
    lat_centers = np.arange(-90.0, 90.0 + dlat, dlat)  # -90, -89, ..., 89, 90

    per_basin = {}
    for name, key in basin_to_key.items():
        moc = tpv.calc_zmoc(mesh, w, dlat=dlat, which_moc=key,
                            diagpath=diagpath, do_info=False, do_compute=True)
        # moc['zmoc']: dims (nz, lat) or (time, nz, lat) if time dim was kept
        per_basin[name] = moc["zmoc"]

    # Figure out time + nz from the first basin result
    first = next(iter(per_basin.values()))
    has_time = "time" in first.dims
    # tripyview may emit either 'nz' or 'nz1' as the vertical dim depending on
    # the diag file's nod_area level convention.
    _zdim = "nz" if "nz" in first.dims else ("nz1" if "nz1" in first.dims else None)
    if _zdim is None:
        raise ValueError(f"compute_msftmz: zmoc result has no vertical dim (dims={first.dims})")
    nz = first.sizes[_zdim]
    ntime = first.sizes["time"] if has_time else 1

    # Match target nz=nz from tripyview; use interface depths from mesh
    lev = np.asarray(mesh.zlev[:nz])  # negative-down, in metres

    out = np.full((ntime, nz, 3, lat_centers.size), np.nan, dtype=np.float64)
    for j, name in enumerate(_CMIP_BASIN_NAMES):
        da = per_basin[name]
        # Align to target lat grid via reindex (NaN outside basin extent)
        da = da.reindex(lat=lat_centers)
        vals = da.values  # (nz,nlat) or (time,nz,nlat)
        if vals.ndim == 2:
            out[0, :, j, :] = vals
        else:
            out[:, :, j, :] = vals

    # tripyview zmoc is in Sv; convert to kg s-1 (1 Sv = 1e9 kg s-1 since ρ₀~1000)
    out_kg = out * 1.0e9

    time_coord = (data["time"].values if isinstance(data, xr.Dataset) and "time" in data.coords
                  else np.arange(ntime))
    # If tripyview collapsed the time dim (because input had none), use 1-element
    if not has_time and ntime == 1 and isinstance(time_coord, np.ndarray) and time_coord.size != 1:
        time_coord = time_coord[:1]

    da_out = xr.DataArray(
        out_kg,
        dims=("time", "lev", "basin", "lat"),
        coords={
            "time": time_coord,
            "lev": lev,
            "basin": list(_CMIP_BASIN_NAMES),
            "lat": lat_centers,
        },
        name=rule.model_variable,
        attrs={"units": "kg s-1",
               "long_name": "Ocean Meridional Overturning Mass Streamfunction"},
    )
    return da_out.to_dataset()


def compute_hfbasin(data, rule):
    """
    Northward ocean heat transport by basin (CMIP hfbasin), W.

    From element-based vtemp (= v·T) produced by FESOM with ldiag_trflx=.true.:
      HT(basin, lat) = ρ₀ · cp · Σ_elems[basin, lat_bin] vtemp · dz · element_area^{1/2}

    This is a zonally-integrated, latitude-binned meridional heat transport.
    Element basin assignment: majority of its 3 node-basins (first non-zero).

    Inputs:
      data: xr.Dataset or DataArray with vtemp (time, nz1, elem)
      rule.grid_file: mesh.nc (for elem lat, area, triangle indices)
      rule.basin_mask_file: node-basin mask
    Output: DataArray (time, basin, lat) in W.
    """
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("compute_hfbasin requires 'grid_file'")
    vt = data["vtemp"] if isinstance(data, xr.Dataset) and "vtemp" in data else data
    ntime = vt.shape[0]
    nz1 = vt.shape[1]

    lat_nodes, area_nodes, depth_bnds, tri = _mesh_nodes(grid_file)
    dz = np.diff(depth_bnds)[:nz1]
    elem_lat, elem_area, elem_dx = _elem_lat_area(lat_nodes, area_nodes, tri)
    min_lat = lat_nodes[tri].min(axis=0)
    max_lat = lat_nodes[tri].max(axis=0)
    basin_nodes = _load_basin_nodes(rule)
    elem_basin = basin_nodes[tri[0]]
    weight_1d = dz[:, None] * elem_dx[None, :] * (_RHO0 * _CP)  # (nz1, elem)

    # stream time-by-time → per-element depth-summed flux, then crossing-sum
    lat_edges = _lat_edges(1.0)
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])
    flux2d = np.empty((ntime, tri.shape[1]), dtype=np.float64)
    for t in range(ntime):
        vt_t = np.asarray(vt.isel(time=t).values)  # (nz1, elem)
        vt_t = np.where(np.isfinite(vt_t), vt_t, 0.0)
        flux2d[t] = (vt_t * weight_1d).sum(axis=0)
    binned = _basin_lat_crossing_sum(flux2d, min_lat, max_lat, elem_basin, lat_centers)
    binned = _aggregate_to_cmip_basins(binned, lat_centers)

    out = xr.DataArray(
        binned,
        dims=("time", "basin", "lat"),
        coords={
            "time": vt["time"].values if "time" in vt.coords else np.arange(binned.shape[0]),
            "basin": list(_CMIP_BASIN_NAMES),
            "lat": lat_centers,
        },
        name=rule.model_variable,
        attrs={"units": "W", "long_name": "Northward Ocean Heat Transport by Basin"},
    )
    return out.to_dataset()


def compute_sltbasin(data, rule):
    """Northward ocean salt transport by basin (CMIP sltbasin), kg s-1.

    Same structure as compute_hfbasin but using usalt/vsalt = v·S (g/kg·m/s).
    Output: ρ₀ · Σ_elems vsalt · dz · edge  [g/s], scaled to kg/s.
    """
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("compute_sltbasin requires 'grid_file'")
    vs = data["vsalt"] if isinstance(data, xr.Dataset) and "vsalt" in data else data
    ntime = vs.shape[0]
    nz1 = vs.shape[1]

    lat_nodes, area_nodes, depth_bnds, tri = _mesh_nodes(grid_file)
    dz = np.diff(depth_bnds)[:nz1]
    elem_lat, elem_area, elem_dx = _elem_lat_area(lat_nodes, area_nodes, tri)
    min_lat = lat_nodes[tri].min(axis=0)
    max_lat = lat_nodes[tri].max(axis=0)
    basin_nodes = _load_basin_nodes(rule)
    elem_basin = basin_nodes[tri[0]]
    # vsalt in psu·m/s = g/kg·m/s; ρ₀·dx·dz·v·S → g/s; /1000 → kg/s
    weight_1d = dz[:, None] * elem_dx[None, :] * _RHO0 / 1000.0

    lat_edges = _lat_edges(1.0)
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])
    flux2d = np.empty((ntime, tri.shape[1]), dtype=np.float64)
    for t in range(ntime):
        vs_t = np.asarray(vs.isel(time=t).values)
        vs_t = np.where(np.isfinite(vs_t), vs_t, 0.0)
        flux2d[t] = (vs_t * weight_1d).sum(axis=0)
    binned = _basin_lat_crossing_sum(flux2d, min_lat, max_lat, elem_basin, lat_centers)
    binned = _aggregate_to_cmip_basins(binned, lat_centers)

    out = xr.DataArray(
        binned,
        dims=("time", "basin", "lat"),
        coords={
            "time": vs["time"].values if "time" in vs.coords else np.arange(binned.shape[0]),
            "basin": list(_CMIP_BASIN_NAMES),
            "lat": lat_centers,
        },
        name=rule.model_variable,
        attrs={"units": "kg s-1", "long_name": "Northward Ocean Salt Transport by Basin"},
    )
    return out.to_dataset()

