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
    broadcast_yearly_to_monthly, clip_small_negatives, clip_floor_zero,
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
    compute_msftm_density, compute_msftmmpa_depth, compute_msftmmpa_density,
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
import re as _re
from typing import Optional

import numpy as np
import pint
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


def compute_areacello(data, rule):
    """
    Ocean grid-cell area from an unstructured mesh.

    Reads ``cell_area`` (or ``cluster_area`` as a fallback) from the mesh
    Dataset produced by ``load_gridfile``. No computation — the mesh
    already stores the per-node surface area in m².

    Input: xr.Dataset (mesh file with ``cell_area`` or ``cluster_area``)
    Output: xr.DataArray (1D, per ocean node)
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


def _layer_thickness_from_bnds(bnds):
    """
    Compute per-level layer thickness from a 1D depth_bnds array of interfaces.

    Robust to malformed mesh files where the trailing interface is corrupt
    (observed on FESOM2 DARS mesh.nc: last depth_bnds entry was a stray 70 m
    that produced a -6180 m diff). Replaces non-positive diffs with NaN so
    sanity checks treat them as missing.
    """
    bnds = np.asarray(bnds, dtype=float)
    thickness = np.diff(bnds)
    bad = ~(thickness > 0)
    if bad.any():
        n_bad = int(bad.sum())
        logger.warning(
            f"Mesh depth_bnds produced {n_bad} non-positive layer thickness(es); "
            f"setting to NaN. Likely a corrupt trailing interface in mesh.nc."
        )
        thickness = np.where(bad, np.nan, thickness)
    return thickness


def compute_thkcello_fx(data, rule):
    """
    Compute static ocean layer thickness from mesh depth bounds.

    For z-coordinate models with fixed levels, thickness = diff(depth_bnds).
    Returns a 1D array of layer thicknesses indexed by level.

    Input: xr.Dataset (mesh file with 'depth_bnds')
    Output: xr.DataArray (1D, per level)
    """
    if "depth_bnds" in data:
        thickness = _layer_thickness_from_bnds(data["depth_bnds"].values)
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
        thickness = _layer_thickness_from_bnds(data["depth_bnds"].values)
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

    sss = _load_secondary_mf(rule, "sss_path", "sss_pattern", "sss_variable")
    h_ice = _load_secondary_mf(rule, "hice_path", "hice_pattern", "hice_variable")

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

    # Sign convention: CMIP `siflcondtop` is the "surface DOWNWARD heat flux
    # in sea ice" (positive = atmosphere -> ice). FESOM's internal "C" term
    # in budget() (ice_thermo_oce.F90:749) uses the opposite sign — it's the
    # heat ARRIVING AT the ice surface FROM BELOW. So we negate here:
    #   q_CMIP_down = -k * (T_base - T_surface)/h = k * (T_surface - T_base)/h
    # In winter T_surface << T_base -> result NEGATIVE (heat going up out of
    # the ice, away from the atmosphere); in summer melt T_surface ~ T_base
    # -> result near 0 or slightly positive.
    result = k_ice * (data - t_base) / h_safe
    result.attrs = {
        "units": "W m-2",
        "standard_name": "surface_downward_heat_flux_in_sea_ice",
        "long_name": "Net Conductive Heat Flux in Sea Ice at the Surface",
        "positive": "down",
        "processing_note": (
            f"k_ice={k_ice} W/m/K, T_base=freezing_point(SSS), T_surface=ist;"
            " sign convention: positive downward (atm -> ice)"
        ),
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

    ist = _load_secondary_mf(rule, "ist_path", "ist_pattern", "ist_variable")
    sss = _load_secondary_mf(rule, "sss_path", "sss_pattern", "sss_variable")

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

    h_snow = _load_secondary_mf(rule, "snow_path", "snow_pattern", "snow_variable")

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

    # Build a per-node weight = hemisphere_mask * cell_area, as a single
    # 1D numpy array. Then ``(data * weight).sum(dim=horizontal_dim)`` is
    # a pure element-wise multiply + reduction — dask-friendly, no fancy
    # indexing, no eager load.
    #
    # Earlier code used ``data.isel({horizontal_dim: hemi_idx})`` with a
    # 1.5M-element fancy index. On dask-backed daily a_ice that produces a
    # task graph with O(time_chunks × hemi_idx) tasks, taking minutes to
    # schedule and causing the deterministic save_dataset hang on the
    # daily NH rules (siarea_*_nh, sisnmass_*_nh, ...). The masking
    # approach below preserves the same math but builds a graph with
    # one task per time chunk.
    lat_vals = lat.values
    if hemisphere.upper() == "N":
        mask = (lat_vals >= 0).astype(np.float64)
    else:
        mask = (lat_vals < 0).astype(np.float64)
    weight = mask * cell_area.values  # m² where in hemi, 0 elsewhere

    # For extent: binarise data to 1 where data > threshold (e.g. a_ice > 0.15)
    # BEFORE the multiplication. Stays dask-friendly.
    if extent_threshold is not None:
        data = (data > float(extent_threshold)).astype(np.float64)

    weight_da = xr.DataArray(weight, dims=[horizontal_dim])
    result = (data * weight_da).sum(dim=horizontal_dim)
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
    ipnd = _load_secondary_mf(rule, "ipnd_path", "ipnd_pattern", "ipnd_variable")
    hpnd = _load_secondary_mf(rule, "hpnd_path", "hpnd_pattern", "hpnd_variable")

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

    if (
        horiz_dim in ("elem",)
        or data.sizes[horiz_dim] > 200000
        and data.sizes[horiz_dim] != hnode.sizes.get("nod2", -1)
    ):
        # Element-based: utemp/vtemp live on triangles; interpolate hnode from 3 corner nodes.
        edge_arr, tri = _elem_geometry(grid_file)
        hnode_node_dim = next(
            (d for d in hnode.dims if hnode.sizes[d] == tri.max() + 1 or d in ("nod2", "ncells")), None
        )
        if hnode_node_dim is None:
            raise ValueError(f"Cannot find node dim in hnode with dims {hnode.dims}")
        hnode_elem = (
            hnode.isel({hnode_node_dim: xr.DataArray(tri[0], dims=[horiz_dim])})
            + hnode.isel({hnode_node_dim: xr.DataArray(tri[1], dims=[horiz_dim])})
            + hnode.isel({hnode_node_dim: xr.DataArray(tri[2], dims=[horiz_dim])})
        ) / 3.0
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


def select_year(data, rule):
    """
    Slice a Dataset / DataArray to a single calendar year along its time
    coordinate.

    Intended for rules that read a long-record forcing file (input4MIPs GHG
    concentrations, prescribed ozone, scenario forcings) but should only
    cmorize one run-year at a time.

    Pass-through if the rule sets neither ``year`` nor ``year_start``.

    Rule attributes:
      - ``year`` (preferred) or ``year_start``: int / str / 4-digit; the
        year to retain on the time axis.

    For piControl-style cases where the model year is *outside* the forcing
    record (e.g. model year 1587 but forcing 1750-2022), use
    ``broadcast_forcing_year_to_monthly`` instead.
    """
    year = _resolve_year(rule)
    if year is None:
        return data
    year_str = str(year)
    for name in ("time", "time_counter", "Time", "TIME", "t"):
        if name in getattr(data, "coords", {}) or name in getattr(data, "dims", ()):
            return data.sel({name: year_str})
    raise ValueError(
        f"select_year: no recognized time coordinate on data "
        f"(looked for time / time_counter / Time / TIME / t); "
        f"got coords={list(getattr(data, 'coords', {}))}"
    )


def broadcast_forcing_year_to_monthly(data, rule):
    """
    Select one reference year from a long forcing record and broadcast it
    to 12 monthly timestamps labeled with the model run year.

    piControl pattern: AWI-ESM3 runs with fixed 1850 GHG forcing perpetually,
    but model calendar years are arbitrary (e.g. 1587). The cmor output must
    contain the 1850 reference values, time-stamped within the model year.
    Replaces the ``select_year`` + ``upsample_to_monthly`` combo for that
    case (upsample-by-ffill produces only 1 record from 1 input, not 12).

    Rule attributes:
      - ``year``: int / str / 4-digit; the model run year (output timestamps).
      - ``forcing_year``: int / str / 4-digit; year to read from the file
        (e.g. 1850 for CMIP piControl reference).
    """
    year = _resolve_year(rule)
    forcing_year = (
        rule.get("forcing_year")
        if hasattr(rule, "get")
        else getattr(rule, "forcing_year", None)
    )
    if year is None or forcing_year is None:
        raise ValueError(
            "broadcast_forcing_year_to_monthly requires both `year` (model "
            "run year, or year_start==year_end via CLI) and `forcing_year` "
            "(year to read from forcing file)"
        )
    year_i = int(year)
    forcing_year_i = int(forcing_year)

    time_name = None
    for name in ("time", "time_counter", "Time", "TIME", "t"):
        if name in getattr(data, "coords", {}) or name in getattr(data, "dims", ()):
            time_name = name
            break
    if time_name is None:
        raise ValueError(
            f"broadcast_forcing_year_to_monthly: no recognized time coord; "
            f"got {list(getattr(data, 'coords', {}))}"
        )

    sliced = data.sel({time_name: str(forcing_year_i)})
    if time_name in getattr(sliced, "dims", ()) and sliced.sizes[time_name] > 1:
        sliced = sliced.mean(time_name, keep_attrs=True)
    sliced = sliced.squeeze(drop=False)
    if time_name in sliced.coords:
        sliced = sliced.drop_vars(time_name)
    if time_name in sliced.dims:
        sliced = sliced.isel({time_name: 0}, drop=True)

    # Build 12 mid-month timestamps for the model run year. Use cftime
    # (proleptic_gregorian) because piControl model years can be outside
    # the datetime64[ns] range (1678-2262) — e.g. AWI-ESM3 spinup at 1587.
    import cftime
    new_times = np.array(
        [
            cftime.DatetimeProlepticGregorian(year_i, m, 16, 12, 0, 0)
            for m in range(1, 13)
        ]
    )
    result = sliced.expand_dims({time_name: new_times})
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

    pso = p_atm + rho_0 * g * ssh  [Pa]

    CMIP `pso` is absolute sea-water pressure at the surface, which equals
    atmospheric loading plus the hydrostatic head from SSH. Without an
    explicit p_atm field, we add a constant reference atmospheric pressure
    (101325 Pa = standard atmosphere) so the output is centred near 1 atm
    rather than around zero.

    Rule attributes (optional):
      - reference_density: float (default 1025.0 kg/m3)
      - gravity: float (default 9.80665 m/s2)
      - reference_atmospheric_pressure: float (default 101325.0 Pa); set
        to 0 to recover the legacy anomaly behaviour.
    """
    rho_0 = float(rule.get("reference_density", 1025.0))
    g = float(rule.get("gravity", 9.80665))
    p_atm = float(rule.get("reference_atmospheric_pressure", 101325.0))
    result = p_atm + rho_0 * g * data
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
    for free-surface ocean models. The geostrophic approximation breaks
    down within ~10° of the equator (|f| ≈ 2.5e-5 1/s), so f_min=2.5e-5
    is the default — Christian's cli37 review flagged a residual
    artifact band at ±4-10° that came from the previous f_min=1e-5
    cutoff (which only masked |lat| < ~4°).

    Primary input (data) is SSH (sea surface height, in metres).

    Rule attributes:
      - grid_file: path to mesh NetCDF file (must contain 'depth'+'depth_lev'
        or 'zbar_n_bottom', and 'lat' or 'latitude')
      - reference_density: Boussinesq rho_0 (default 1025.0 kg/m3)
      - gravity: g (default 9.80665 m/s2)
      - omega: Earth's angular velocity (default 7.2921e-5 rad/s)
      - f_min: minimum |f| cutoff for equatorial masking (default
        2.5e-5 1/s = ±~10° latitude; widen further if downstream tools
        still show non-physical equatorial spikes)
    """
    rho_0 = float(rule.get("reference_density", 1025.0))
    g = float(rule.get("gravity", 9.80665))
    omega = float(rule.get("omega", 7.2921e-5))
    f_min = float(rule.get("f_min", 2.5e-5))

    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for compute_msftbarot step")

    mesh = xr.open_dataset(grid_file)

    # --- Ocean floor depth H (positive downward) ---
    if "depth_lev" in mesh and "depth" in mesh:
        depth_vals = mesh["depth"].values
        depth_lev = mesh["depth_lev"].values
        H = np.array([depth_vals[min(int(nl) - 1, len(depth_vals) - 1)] if nl > 0 else 0.0 for nl in depth_lev])
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
            f"f_min={f_min} 1/s (NaN in equatorial band where the "
            f"geostrophic balance breaks down)."
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
    The other component is loaded via the standard path/pattern triplet.

    Rule attributes:
      - second_input_path: directory containing the other component files
      - second_input_pattern: regex matching the filenames
      - second_variable: variable name (default: auto-detect)
    """
    v2 = _load_secondary_mf(
        rule, "second_input_path", "second_input_pattern", "second_variable"
    )

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
    Compute sea ice mass transport: velocity × ice mass × cell width.

    CMIP ``sidmasstranx`` / ``sidmasstrany`` are in ``kg s-1`` — the total
    sea-ice mass crossing a cell edge per unit time, not a mass flux per
    unit edge length. The physical formula is

        sidmasstran = uice [m/s] × m_ice [m] × rho_ice [kg/m³]
                    × cell_width_perp [m]

    On a regular grid ``cell_width_perp`` is dy (for x-transport) or dx
    (for y-transport). On FESOM's unstructured mesh there is no clean
    anisotropic edge width per node, so we use the isotropic
    approximation ``sqrt(cell_area)`` — this is what's available in the
    mesh file and matches the FESOM community convention for reporting
    node-level transports on a regular CMIP grid.

    FESOM's ``m_ice`` is *effective ice height per unit area* (units 'm';
    see ice/io_meandata.F90 def_stream long_name "ice height per unit
    area"), so ``m_ice × rho_ice`` converts to mass per area. AOMIP
    ``rho_ice = 910 kg/m³`` is the FESOM default (MOD_ICE.F90:61);
    override via ``rho_ice`` on the rule.

    Without ``cell_width_perp`` and ``rho_ice``, the legacy formula
    ``uice × m_ice`` returned ``m²/s`` mislabelled as ``kg/s`` — values
    were ~5 orders of magnitude too low at TCo319/DARS resolution.

    Rule attributes:
      - mice_path / mice_pattern: m_ice files (required)
      - mice_variable: variable name (default: 'm_ice')
      - rho_ice: ice density, kg/m³ (default 910.0, FESOM AOMIP)
      - grid_file: FESOM mesh.nc containing ``cell_area`` (required)
      - fesom_node_dim: name of node dimension (default: 'nod2')

    FESOM writes ``uice``/``vice`` daily and ``m_ice`` monthly when the run
    is configured with mixed-cadence ice diagnostics. xarray's coord-value
    alignment then leaves a sparse intersection (typically 0 timestamps)
    and downstream ``timeavg`` errors with a CoordinateValidationError.
    Resample the velocity to the m_ice cadence before multiplying so both
    sides agree on time.
    """
    rho_ice = float(rule.get("rho_ice", 910.0))
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError(
            "Rule must specify 'grid_file' for compute_ice_mass_transport "
            "(needs cell_area to scale by cell width perpendicular to flow)"
        )

    m_ice = _load_secondary_mf(rule, "mice_path", "mice_pattern", "mice_variable")

    # Coarsen whichever side is finer to monthly. m_ice is the canonical
    # FESOM mass cadence (monthly); uice/vice can be daily under high-rate
    # ice diagnostics — average them to monthly so the multiplication
    # broadcasts cleanly.
    data_time = _find_time_dim(data)
    mice_time = _find_time_dim(m_ice)
    if data_time and mice_time and data.sizes.get(data_time) != m_ice.sizes.get(mice_time):
        if data.sizes[data_time] > m_ice.sizes[mice_time]:
            data = data.resample({data_time: "MS"}).mean()
    m_ice = _resample_to_match(data, m_ice)

    mesh = xr.open_dataset(grid_file)
    edge_width = _fesom_edge_width(mesh, data)
    mesh.close()
    if edge_width is None:
        raise ValueError(
            "Mesh file must contain 'cell_area' (m²) aligned to data's "
            "horizontal dimension; effective edge width = sqrt(cell_area) "
            "is required to convert ice transport from m²/s to kg/s."
        )

    result = data * m_ice * rho_ice * edge_width
    result.attrs = data.attrs.copy()
    result.attrs["units"] = "kg s-1"
    result.attrs["processing_note"] = (
        f"sidmasstran = uice * m_ice * rho_ice({rho_ice}) * sqrt(cell_area). "
        f"FESOM m_ice is effective ice height per cell area [m]; "
        f"sqrt(cell_area) is the isotropic Voronoi-cell edge width."
    )
    result.name = data.name
    return result


def compute_sfdsi_from_fw_ice(data, rule):
    """
    Reconstruct CMIP sfdsi (Downward Sea Ice Basal Salt Flux) from the
    sea-ice freshwater flux fw_ice and the surface salinity sss.

    Under linfs (use_virt_salt=.true.) FESOM never populates real_salt_flux
    (the assignment in ice_thermo_cpl.F90 is gated by ``.not. use_virt_salt``),
    so the legacy `sfdsi=realsalt` recipe produces a field of zeros. The
    physical salt flux from sea-ice freeze/melt is instead reconstructed
    from the ice freshwater flux and the local surface salinity:

        sfdsi = -rho_w · (sss/1000) · fw_ice

    Sign convention:
      - freezing  → fw_ice < 0 → sfdsi > 0 (salt rejected INTO ocean)
      - melting   → fw_ice > 0 → sfdsi < 0 (dilution = salt LOST to ocean)

    Units: ``fw_ice`` is ``m s-1`` (volume flux of freshwater per area),
    ``sss`` is ``g kg-1`` (psu), ``rho_w`` is ``kg m-3``; result is
    ``kg salt m-2 s-1``.

    Primary input (``data``): ``fw_ice``.
    Rule attributes:
      - sss_file: glob pattern for FESOM sss file(s) (required)
      - sss_variable: variable name in those files (default: 'sss')
      - reference_density: rho_w (default 1025.0 kg/m³)
    """
    rho_w = float(rule.get("reference_density", 1025.0))
    sss = _load_secondary_mf(rule, "sss_path", "sss_pattern", "sss_variable")
    # FESOM writes sss daily but fw_ice monthly; coarsen sss to monthly so
    # the multiplication broadcasts cleanly. _align_time_to alone leaves the
    # cadence mismatch (12 vs 365) and xarray then aligns on coord-value
    # intersection (7-of-12 mid-month overlaps), which downstream timeavg
    # rejects as a 12-vs-7 CoordinateValidationError.
    sss = _resample_to_match(data, sss)

    result = -rho_w * (sss / 1000.0) * data
    result.attrs = {
        "units": "kg m-2 s-1",
        "standard_name": "downward_sea_ice_basal_salt_flux",
        "long_name": "Downward Sea Ice Basal Salt Flux",
    }
    result.name = rule.model_variable
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
    sgm22 = _load_secondary_mf(rule, "sgm22_path", "sgm22_pattern", "sgm22_variable")

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
    sgm22 = _load_secondary_mf(rule, "sgm22_path", "sgm22_pattern", "sgm22_variable")
    sgm12 = _load_secondary_mf(rule, "sgm12_path", "sgm12_pattern", "sgm12_variable")

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


def _fesom_edge_width(mesh, data, horiz_dim_candidates=("nod2", "ncells", "ncol")):
    """Return per-node effective edge width (m) as an xr.DataArray, or None.

    CMIP7 wants mass/salt transport in `kg s-1` (integrated across the cell
    edge perpendicular to the flow). FESOM 2.7's DARS2 mesh doesn't expose
    an explicit edge-length variable; it has `cell_area` (node Voronoi-cell
    area, m²). The effective edge width ≈ sqrt(cell_area) — exact for
    squares, order-of-magnitude correct for irregular Voronoi cells, and
    the convention used by AWI for CMIP6 FESOM submissions.

    Aligns the returned DataArray to the data's horizontal dim name.
    """
    if "cell_area" not in mesh:
        return None
    horiz_dim = next(
        (d for d in data.dims if d in horiz_dim_candidates), None
    )
    if horiz_dim is None:
        return None
    cell_area = mesh["cell_area"]
    if int(cell_area.size) != int(data.sizes[horiz_dim]):
        return None
    edge_width = np.sqrt(np.asarray(cell_area.values, dtype=float))
    return xr.DataArray(edge_width, dims=[horiz_dim])


def average_w_interfaces_to_midpoints(data, rule):
    """
    Average FESOM ``w`` from layer interfaces to cell-center midpoints,
    matching the CMIP convention for ``wo``.

    FESOM 2.7 emits ``w`` on the top N layer interfaces (N=57 for the
    DARS mesh: surface at z=0 through the top of the deepest layer).
    The mesh has N cell-centre midpoints between N+1 interfaces; only
    the top N interfaces are stored, the bottom-most (seabed) being
    implicitly w=0 (flat-seabed BC).

    cli37's bare passthrough wrote w on the 57 interface depths
    ``[0, 5, 10, 20, 30, …, 6250]`` but labelled the coord with
    ``olevel:name = "nz1"`` (the midpoint name). Reviewers (Christian)
    flagged the result: "uppermost layer not too bad, those below are
    noisy". That's exactly what an interface emission produces — the
    surface BC (w=0 at interface 0) is preserved literally, while every
    deeper interface carries the diagnostic-w noise from integrating
    horizontal divergence down from the surface.

    This step folds adjacent interfaces into midpoints so:
      - the surface BC is averaged into the first midpoint (no more
        "clean top, noisy below" jump);
      - the vertical coord becomes mesh.depth (the CMIP midpoint axis);
      - the output has the same number of levels as the mesh has cells
        (57 here), so downstream CMOR validation matches.

    Formula:
      midpoint[i] = 0.5 * (w[i] + w[i+1])      for i = 0 … N-2
      midpoint[N-1] = 0.5 * w[N-1]              (bottom BC w_seabed=0)

    Rule attributes:
      - grid_file: FESOM mesh netCDF (needs ``depth`` for midpoint
        coords and ``depth_bnds`` for the N-vs-N+1 sanity check)
    """
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError(
            "Rule must specify 'grid_file' for average_w_interfaces_to_midpoints"
        )

    if not isinstance(data, xr.DataArray):
        raise ValueError(
            "average_w_interfaces_to_midpoints expects an xr.DataArray"
        )

    vertical_dim = next(
        (d for d in ("nz", "nz1", "lev", "depth", "olevel") if d in data.dims),
        None,
    )
    if vertical_dim is None:
        raise ValueError(
            f"No vertical dimension found in data dims={list(data.dims)}"
        )

    mesh = xr.open_dataset(grid_file)
    if "depth" not in mesh:
        mesh.close()
        raise ValueError("Mesh file must contain 'depth' (midpoint coords)")
    midpoint_depth = np.asarray(mesh["depth"].values, dtype=float)
    n_midpoints = midpoint_depth.size
    mesh.close()

    nz_data = data.sizes[vertical_dim]
    if nz_data != n_midpoints:
        raise ValueError(
            f"Expected vertical size {n_midpoints} (FESOM cell layers, "
            f"matches mesh 'depth'); got {nz_data}"
        )

    # Pad the deepest interface with zero (bottom BC: w=0 at seabed),
    # then average adjacent interfaces to get midpoints.
    upper = data
    lower = xr.concat(
        [
            data.isel({vertical_dim: slice(1, None)}),
            xr.zeros_like(data.isel({vertical_dim: 0})).expand_dims(
                {vertical_dim: 1}
            ),
        ],
        dim=vertical_dim,
    )
    # Strip stale interface coords on `lower` so the addition doesn't
    # trigger an axis-value mismatch.
    lower = lower.assign_coords({vertical_dim: upper[vertical_dim].values})
    result = 0.5 * (upper + lower)

    # Replace the interface coord with midpoint depths and rename the
    # dim to the canonical CMIP midpoint name so downstream
    # set_coordinates / map_dimensions sees the expected axis.
    #
    # On the DARS mesh the deepest "midpoint" in mesh.depth is a seabed
    # boundary artefact: depths run monotonically through index N-2
    # (e.g. 6125 m) and then drop back at index N-1 (e.g. 3160 m). The
    # corresponding w-midpoint is just 0.5*w[N-1] (the synthetic seabed
    # BC) so it has no physics either. Trim it so the vertical coord
    # is strictly monotonic — CF §1.2.
    diffs = np.diff(midpoint_depth)
    if not (np.all(diffs > 0) or np.all(diffs < 0)):
        n_keep = 1 + int(np.argmin(diffs > 0)) if diffs[0] > 0 else 1 + int(np.argmin(diffs < 0))
        result = result.isel({vertical_dim: slice(0, n_keep)})
        midpoint_depth = midpoint_depth[:n_keep]
    result = result.assign_coords({
        vertical_dim: xr.DataArray(
            midpoint_depth,
            dims=(vertical_dim,),
            attrs={
                "long_name": "ocean depth",
                "standard_name": "depth",
                "units": "m",
                "axis": "Z",
                "positive": "down",
            },
        ),
    })
    if vertical_dim != "nz1":
        result = result.rename({vertical_dim: "nz1"})

    result.attrs = dict(data.attrs)
    result.attrs["processing_note"] = (
        "Averaged from FESOM w on the top N layer interfaces (i.e. layer "
        "tops, surface at z=0) to N cell-centre midpoints. Bottom BC "
        "w_seabed=0 assumed for the deepest midpoint. Surface BC w=0 "
        "folded into the first midpoint, eliminating the 'clean top, "
        "noisy below' artefact."
    )
    result.name = data.name
    return result


def compute_mass_transport(data, rule):
    """
    Compute ocean mass transport from velocity.

    Horizontal (transport_component in {'x','y'}):
      mass_transport = u * rho_0 * dz * sqrt(cell_area)
      Units: m/s * kg/m³ * m * m = kg/s, integrated across the cell's
      Voronoi-edge perpendicular to the flow.

    Vertical (transport_component == 'z'):
      mass_transport = w * rho_0 * cell_area
      Units: m/s * kg/m³ * m² = kg/s, integrated across the horizontal
      face of the cell. (The horizontal formula's `dz * sqrt(cell_area)`
      term is the wrong area for the vertical face — using it for `w`
      undercounts by ~dz/sqrt(cell_area), which at FESOM HR resolution
      is ~50 m / 1e4 m = ~200x too small.)

    Rule attributes:
      - reference_density: Boussinesq rho_0 (default 1025.0 kg/m3)
      - transport_component: 'x', 'y', or 'z' (controls area factor)
      - grid_file: path to FESOM mesh netCDF (needs `depth_bnds` and
        `cell_area`)
    """
    rho_0 = float(rule.get("reference_density", 1025.0))
    grid_file = rule.get("grid_file")
    component = rule.get("transport_component", "")

    # data is a DataArray (velocity field, already extracted by get_variable)
    if not isinstance(data, xr.DataArray):
        raise ValueError("compute_mass_transport expects velocity as xr.DataArray")

    # Get layer thickness and cell-edge width / cell area from mesh
    mesh = xr.open_dataset(grid_file)
    if "depth_bnds" in mesh:
        depth_bnds = mesh["depth_bnds"].values
        dz = np.diff(depth_bnds)
    else:
        mesh.close()
        raise ValueError("Mesh file must contain 'depth_bnds' for layer thickness")
    edge_width = _fesom_edge_width(mesh, data)
    # cell_area is needed verbatim for vertical mass flux (horizontal face)
    horiz_dim_for_area = next((d for d in data.dims if d in ("nod2", "ncells", "ncol")), None)
    if str(component).lower() == "z" and horiz_dim_for_area is not None and "cell_area" in mesh:
        cell_area = xr.DataArray(
            np.asarray(mesh["cell_area"].values, dtype=float),
            dims=[horiz_dim_for_area],
        )
    else:
        cell_area = None
    mesh.close()
    if edge_width is None:
        raise ValueError(
            "Mesh file must contain 'cell_area' (m²) aligned to data's "
            "horizontal dimension; effective edge width = sqrt(cell_area) "
            "is required to convert transport from kg/(s*m) to kg/s."
        )

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
            f"W-level data detected ({nz_data} levels vs {len(dz)} layers). " f"Averaging interfaces to cell centers."
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

    # Vertical mass transport (Omon.wmo): the area is the horizontal cell
    # face, not the vertical Voronoi-edge. Use cell_area directly.
    # Horizontal mass transport (Omon.{umo,vmo}): integrate across the
    # vertical face = dz * sqrt(cell_area).
    if str(component).lower() == "z" and cell_area is not None:
        transport = data * rho_0 * cell_area
        area_note = "cell_area (horizontal face)"
    else:
        transport = data * rho_0 * thickness * edge_width
        area_note = "dz * sqrt(cell_area) (vertical face perpendicular to flow)"

    transport.name = data.name
    transport.attrs = {
        "units": "kg s-1",
        "processing_note": (
            f"Computed as velocity * rho_0({rho_0}) * {area_note}. "
            f"Integrated mass transport across grid-cell {component}-face."
        ),
    }
    return transport


def compute_salt_transport(data, rule):
    """
    Compute 3D ocean salt mass transport from velocity and salinity.

    sfx = u * S * rho_0 * dz * sqrt(cell_area)  (x-component, kg s-1)
    sfy = v * S * rho_0 * dz * sqrt(cell_area)  (y-component, kg s-1)

    Salt (S) from FESOM is in psu (g/kg); converted to kg/kg by * 1e-3.
    Result is integrated salt mass transport across the Voronoi-cell edge
    (kg s-1) as CMIP7 Omon.{sfx,sfy} require — same edge-width treatment
    as compute_mass_transport.

    Rule attributes:
      - grid_file: path to FESOM mesh (needs `depth_bnds` and `cell_area`)
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

    # Load layer thickness and cell-edge width from mesh
    mesh = xr.open_dataset(grid_file)
    if "depth_bnds" not in mesh:
        mesh.close()
        raise ValueError("Mesh file must contain 'depth_bnds' for layer thickness")
    dz = np.diff(mesh["depth_bnds"].values)
    edge_width = _fesom_edge_width(mesh, data)
    mesh.close()
    if edge_width is None:
        raise ValueError(
            "Mesh file must contain 'cell_area' (m²) aligned to data's "
            "horizontal dimension; effective edge width = sqrt(cell_area) "
            "is required to convert transport from kg/(s*m) to kg/s."
        )

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

    # Convert psu → kg/kg, then compute integrated transport.
    # sfx [kg s-1] = u [m/s] * S [kg/kg] * rho_0 [kg/m3] * dz [m] * w [m]
    salt_kgkg = salt * 1e-3
    transport = data * salt_kgkg * rho_0 * thickness * edge_width

    component = rule.get("transport_component", "")
    transport.name = data.name
    transport.attrs = {
        "units": "kg s-1",
        "processing_note": (
            f"Computed as velocity * (salt*1e-3) * rho_0({rho_0}) * dz "
            f"* sqrt(cell_area). Integrated salt transport across "
            f"grid-cell {component}-face."
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
        "processing_note": (f"Vertically integrated salt transport (sum over depth). " f"Component: {component}."),
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
    if rule.get("salt_path") and rule.get("salt_pattern"):
        salt = _load_secondary_mf(rule, "salt_path", "salt_pattern", "salt_variable")
    else:
        # Assume constant salinity of 35 psu for thermosteric-only
        salt = xr.full_like(data, 35.0)
        logger.warning(
            "No salt_path/salt_pattern specified, using constant S=35 for thermosteric computation"
        )

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

        # Update units: multiply input units by thickness units (default m).
        # Without this, downstream ``handle_unit_conversion`` sees the unchanged
        # input units (e.g. "W m-2") and fails dimensional checks against the
        # CMIP target (e.g. "W m-1") with a DimensionalityError.
        #
        # Pint cannot parse CF/UDUNITS-style "W m-2" directly (treats "-2" as
        # subtraction); normalise to "W*m**-2" first via _udunits_to_pint.
        input_units = data.attrs.get("units")
        if input_units:
            try:
                ureg = pint.UnitRegistry()
                thickness_units = (
                    thickness.attrs.get("units")
                    if hasattr(thickness, "attrs")
                    else None
                ) or "m"
                new_units = (
                    ureg.parse_expression(_udunits_to_pint(input_units))
                    * ureg.parse_expression(_udunits_to_pint(thickness_units))
                )
                integrated.attrs["units"] = f"{new_units.units:~}"
            except Exception as exc:
                logger.warning(
                    f"vertical_integrate: could not derive output units from "
                    f"{input_units!r} * thickness; leaving units attr unset ({exc})"
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


_TIME_DIM_ALIASES = ("time", "time_counter", "time_centered", "valid_time", "t")


def _find_time_dim(da):
    """Return the first conventional time-dim name present on ``da`` (or None)."""
    return next((n for n in _TIME_DIM_ALIASES if n in da.dims), None)


def _udunits_to_pint(u):
    """Translate CF/UDUNITS-style unit strings to pint-friendly form.

    Pint 0.24 parses ``W m-2`` as ``W * m - 2`` (binary subtraction),
    raising DimensionalityError on the integer literal. Convert each
    ``<letter><signed-int>`` token to ``<letter>**<signed-int>`` and turn
    spaces into multiplication so pint sees ``W*m**-2``.
    """
    return _re.sub(r"([a-zA-Z])(-?\d+)", r"\1**\2", u).replace(" ", "*")


def _align_time_to(primary, secondary):
    """Force ``secondary``'s time coord to match ``primary``'s.

    OIFS XIOS streams label hourly fields by ``online_operation``: instantaneous
    (``_pt_*``) at the top of the hour, hourly-mean (``_sfc_*``) at the mid-hour
    point. Same 8760 samples, different labels — xarray's coord-value-based
    broadcast then sees an empty intersection and downstream steps error
    (``__resample_dim__ must not be empty``). Drop secondary's time coord and
    rebind to primary's so broadcasting matches by index when the cardinalities
    agree.

    Tolerates a 1-2 stamp trailing-end mismatch (the typical
    boundary-spill case where pycmor's data-level year filter trimmed
    the primary's last stamp but not the secondary's, because their
    label conventions differ — e.g. ``_pt_`` top-of-hour vs ``_sfc_``
    mid-hour). Truncates the secondary's trailing stamps to match.
    Larger mismatches are recipe-level cadence problems and return
    unchanged.
    """
    p = _find_time_dim(primary)
    s = _find_time_dim(secondary)
    if p is None or s is None:
        return secondary
    np_, ns = primary.sizes.get(p), secondary.sizes.get(s)
    if np_ != ns:
        if 0 < (ns - np_) <= 2:
            secondary = secondary.isel({s: slice(0, np_)})
        else:
            return secondary
    if s != p:
        secondary = secondary.rename({s: p})
    return secondary.assign_coords({p: primary[p].values})


def _resample_to_match(primary, secondary):
    """Down-sample ``secondary`` to ``primary``'s time cadence, then align.

    Used by compute steps that combine FESOM streams of different cadences
    (e.g. monthly fw_ice × daily sss for sfdsi, or daily uice × monthly m_ice
    for sidmasstran). When ``primary`` is monthly (12) and ``secondary`` is
    daily/hourly (365/8760), averages secondary down to monthly. After the
    cadence is matched, runs ``_align_time_to`` so the resulting coord
    values match primary exactly (avoiding xarray's intersection-on-coord
    alignment that otherwise leaves a sparse 7-of-12 timestamp result).

    No-op if cardinalities already match — ``_align_time_to`` will then
    just rebind labels. If primary is finer than secondary, returns
    secondary unchanged (caller must opt into upsampling explicitly).
    """
    p = _find_time_dim(primary)
    s = _find_time_dim(secondary)
    if p is None or s is None:
        return secondary
    np_, ns = primary.sizes.get(p), secondary.sizes.get(s)
    if np_ == ns:
        return _align_time_to(primary, secondary)
    if np_ < ns:
        secondary = secondary.resample({s: "MS"}).mean()
        return _align_time_to(primary, secondary)
    return secondary


def _resolve_year(rule):
    """Return the cmorize year as int, or None if unresolvable.

    Preference order:
      1. ``rule.year`` (legacy / explicit attribute, set by the old
         repoint_hr_year.py flow or by manual yaml override).
      2. ``rule.year_start`` when ``year_start == year_end`` (CLI
         single-year case post commit 8046000).
      3. None (multi-year chunked dispatch — caller handles by
         iterating per chunk year).

    Single source of truth so the two consumers (``select_year``,
    ``broadcast_forcing_year_to_monthly``) cannot drift apart on the
    fallback semantics.
    """
    if not hasattr(rule, "get"):
        return None
    y = rule.get("year")
    if y is not None:
        return int(y)
    ys, ye = rule.get("year_start"), rule.get("year_end")
    if ys is not None and ys == ye:
        return int(ys)
    return None


import functools as _functools


@_functools.lru_cache(maxsize=16)
def _load_secondary_mf_cached(path, pattern, variable_name, year_start, year_end,
                              skip_filter, time_dimname):
    """Inner cache for ``_load_secondary_mf``. Keyed on the resolved
    lookup tuple (not on the rule object, which isn't hashable). The
    returned DataArray must not be mutated by callers — wrap it with
    ``.copy(deep=False)`` before handing to downstream steps.

    LRU eviction is automatic at ``maxsize`` entries; evicted entries
    drop their DataArray reference and Python GC closes the underlying
    file when the last reference goes away. The expected working-set
    size per cmor flow is well under 16 (a tier typically has 1-3
    distinct secondary inputs shared across many rules).

    Thread safety: CPython's ``lru_cache`` uses RLock; concurrent
    cache-miss callers for the same key serialise — only one
    ``open_mfdataset`` call per key.

    See ``FORENSIC_lrcs_seaice_failure.md`` §"Fix #2" for the
    motivation (a_ice was being loaded 7× per cli16 batch).
    """
    regex = _re.compile(pattern)
    files = sorted(_os.path.join(path, f) for f in _os.listdir(path) if regex.fullmatch(f))
    if not files:
        raise FileNotFoundError(f"No files matching regex {pattern!r} in {path}")
    if year_start is not None and year_end is not None and not skip_filter:
        from pycmor.core.gather_inputs import filter_files_by_year_range

        files = filter_files_by_year_range(files, year_start, year_end)
        if not files:
            raise FileNotFoundError(
                f"No files matching {pattern!r} in {path} fall within "
                f"year range {year_start}–{year_end}"
            )
    ds = xr.open_mfdataset(files, use_cftime=True)
    if time_dimname and time_dimname in ds.dims and "time" not in ds.dims:
        ds = ds.rename({time_dimname: "time"})
    for _drop_var in ["time_counter", "time_centered", "time_counter_bounds", "time_centered_bounds"]:
        if _drop_var in ds.coords and _drop_var != "time":
            ds = ds.drop_vars(_drop_var, errors="ignore")
    if variable_name and variable_name in ds:
        result = ds[variable_name]
    else:
        _BOUNDS_SUFFIXES = ("_bounds", "_bnds", "_bounds_lat", "_bounds_lon")
        data_vars = [
            v for v in ds.data_vars
            if v not in ds.coords
            and not any(str(v).endswith(s) for s in _BOUNDS_SUFFIXES)
            and "axis_nbounds" not in ds[v].dims
            and "nvertex" not in ds[v].dims
        ]
        if not data_vars:
            raise ValueError(
                f"No data variables found in files matching {pattern!r} in {path}"
            )
        result = ds[data_vars[0]]
    return result


def _load_secondary_mf_clear_cache():
    """Drop all cached secondary inputs. Call between cmor flows to
    release file handles. Within a single flow the cache is
    intentionally kept across rule batches."""
    _load_secondary_mf_cached.cache_clear()


def _load_secondary_mf(rule, path_key, pattern_key, variable_key):
    """Load a secondary input variable from a glob pattern of files.

    Cached at module level keyed on the resolved (path, pattern,
    variable, year-range, skip-filter, time-dim-name) tuple — repeat
    calls within a flow that need the same data return without
    reopening the files. Returns a shallow ``.copy()`` so downstream
    rename/select operations don't mutate the cached array.

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
    var_name = rule.get(variable_key)
    year_start = rule.get("year_start")
    year_end = rule.get("year_end")
    skip_filter = bool(rule.get("skip_input_year_filter", False))
    time_dimname = rule.get("time_dimname")
    da = _load_secondary_mf_cached(
        path, pattern, var_name,
        year_start, year_end, skip_filter, time_dimname,
    )
    # Shallow copy so callers can rename / drop / slice without
    # mutating the cache entry. dask graph stays shared with the
    # cached entry — no data copy.
    return da.copy(deep=False)


# Legacy path retained below for any callers still using the un-cached
# semantics; switching them to the new path will be a follow-up cleanup.
def _load_secondary_mf_uncached(rule, path_key, pattern_key, variable_key):
    """Pre-cache implementation of ``_load_secondary_mf``. Kept for
    reference / migration; new code should call ``_load_secondary_mf``.
    """
    path = rule.get(path_key)
    pattern = rule.get(pattern_key)
    if path is None or pattern is None:
        raise ValueError(f"Rule must specify '{path_key}' and '{pattern_key}'")
    regex = _re.compile(pattern)
    files = sorted(_os.path.join(path, f) for f in _os.listdir(path) if regex.fullmatch(f))
    if not files:
        raise FileNotFoundError(f"No files matching regex {pattern!r} in {path}")
    year_start = rule.get("year_start")
    year_end = rule.get("year_end")
    skip_filter = rule.get("skip_input_year_filter", False)
    if year_start is not None and year_end is not None and not skip_filter:
        from pycmor.core.gather_inputs import filter_files_by_year_range

        files = filter_files_by_year_range(files, year_start, year_end)
        if not files:
            raise FileNotFoundError(
                f"No files matching {pattern!r} in {path} fall within "
                f"year range {year_start}–{year_end}"
            )
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
        # Filter out bounds/auxiliary variables so the fallback picks the
        # actual scientific field. FESOM files list ``time_bounds`` before
        # the main variable in the netCDF; without this filter the auto-pick
        # returns time_bounds (shape (time, axis_nbounds)) and downstream
        # arithmetic blows up with object-dtype broadcast errors.
        _BOUNDS_SUFFIXES = ("_bounds", "_bnds", "_bounds_lat", "_bounds_lon")
        data_vars = [
            v for v in ds.data_vars
            if v not in ds.coords
            and not any(str(v).endswith(s) for s in _BOUNDS_SUFFIXES)
            and "axis_nbounds" not in ds[v].dims
            and "nvertex" not in ds[v].dims
        ]
        if not data_vars:
            raise ValueError(
                f"No primary data variable found in {files[0]} after filtering "
                f"bounds/auxiliary; specify '{variable_key}' on the rule."
            )
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


def _e_sat_cmip(T_K):
    """CMIP7-compliant saturation vapour pressure [Pa] as a function of T [K].

    Convention: over water for T >= 273.15 K, over ice for T < 273.15 K
    (CF/CMIP standard). Alduchov & Eskridge (1996) Magnus-form coefficients.
      water:  e_sat = 611.2 * exp(17.625 * Tc / (Tc + 243.04))
      ice:    e_sat = 611.2 * exp(22.587 * Tc / (Tc + 273.86))
    """
    Tc = T_K - 273.15
    e_water = 611.2 * np.exp(17.625 * Tc / (Tc + 243.04))
    e_ice = 611.2 * np.exp(22.587 * Tc / (Tc + 273.86))
    return xr.where(T_K >= 273.15, e_water, e_ice)


def compute_hurs(data, rule):
    """
    Compute near-surface relative humidity from temperature and dewpoint.

    Uses CMIP7 phase-dependent saturation vapour pressure: over water for
    T >= 0°C, over ice for T < 0°C. RH is e_sat(Td) / e_sat(T).

    Primary input (data) is 2t (2m temperature, K).
    Dewpoint is loaded from rule attributes.

    Rule attributes:
      - second_input_path: directory containing dewpoint files
      - second_input_pattern: glob pattern for dewpoint files
      - second_variable: variable name in dewpoint files
    """
    td_K = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")

    # Phase reference follows ambient T (not Td) per CMIP/CF convention.
    e = _e_sat_cmip(td_K)
    e_sat = _e_sat_cmip(data)
    result = 100.0 * e / e_sat
    result = result.clip(0, 100)

    result.attrs = {
        "units": "%",
        "standard_name": "relative_humidity",
        "long_name": "Near-Surface Relative Humidity",
    }
    result.name = rule.model_variable
    return result


def compute_hur_plev(data, rule):
    """Compute CMIP7-compliant relative humidity on pressure levels.

    Uses ta (primary) + hus (secondary); pressure is taken from the
    `plev` coordinate of the input (pfull == plev on pressure levels).
    Saturation vapour pressure follows the CMIP7 convention: over water
    for T >= 0°C, over ice below (see `_e_sat_cmip`). This replaces the
    IFS FullPos `r` field, which uses a mixed-phase QSAT interpolation
    that is not CMIP7-compliant.
    """
    hus = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")
    # pfull from the pressure-level coord; broadcast over (time,lat,lon)
    plev_name = next(
        (
            n
            for n in ("plev", "plev19", "plev39", "plev7h", "plev8", "pressure_levels", "pressure", "lev")
            if n in data.coords
        ),
        None,
    )
    if plev_name is None:
        raise ValueError(f"compute_hur_plev: no plev-like coord on ta (coords={list(data.coords)})")
    pfull = data[plev_name]

    e_sat = _e_sat_cmip(data)
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


def compute_hur_ml(data, rule):
    """
    Compute relative humidity on model levels from ta, hus, pfull.

    OpenIFS on native model levels does not fill the `r` field (FullPos only
    emits `r` on pressure levels). We reconstruct RH with CMIP7 phase-dependent
    saturation vapour pressure (over water for T >= 0°C, over ice below).

      e      = q * p / (0.622 + 0.378 * q)      [Pa]
      e_sat  = phase-dependent Magnus (see _e_sat_cmip)
      RH     = 100 * e / e_sat

    Primary input (data) is ta (air temperature on model levels, K).
    Specific humidity and pressure are loaded from rule attributes.
    """
    hus = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")
    pfull = _load_secondary_mf(rule, "third_input_path", "third_input_pattern", "third_variable")

    e_sat = _e_sat_cmip(data)
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
    sp = _align_time_to(data, sp)

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


def slice_to_rule_year_range(data, rule):
    """Slice the time dimension to keep only ``rule.year_start`` ..
    ``rule.year_end`` inclusive.

    LPJ-GUESS .out files contain every year inline; the loader returns
    them all. Without this step, pycmor emits cmorized output files for
    every year on disk (cli57 leaked 152 monthly files per year for
    years 1850, 1852-1857 when only 1851 was requested).

    No-op when neither bound is set, when there is no time-like
    dimension, or when the data is not an xarray container.
    """
    import pandas as pd

    year_start = getattr(rule, "year_start", None)
    year_end = getattr(rule, "year_end", None)
    if year_start is None and year_end is None:
        return data

    # Find the time-like dim/coord on the data.
    time_name = None
    for candidate in ("time", "time_counter", "Time"):
        if hasattr(data, "coords") and candidate in data.coords:
            time_name = candidate
            break
        if hasattr(data, "dims") and candidate in getattr(data, "dims", ()):
            time_name = candidate
            break
    if time_name is None:
        return data

    times = data[time_name].values
    # Convert each timestamp to a year integer. Accepts cftime, numpy
    # datetime64, and pandas Timestamp without forcing conversion.
    years = np.fromiter((pd.Timestamp(t).year if hasattr(t, "year") is False else t.year
                        for t in times), dtype=np.int64, count=len(times))

    lo = year_start if year_start is not None else years.min()
    hi = year_end if year_end is not None else years.max()
    mask = (years >= lo) & (years <= hi)
    if mask.all():
        return data
    if not mask.any():
        logger.warning(
            f"slice_to_rule_year_range: rule {getattr(rule, 'name', '<?>')} has "
            f"no time steps in range [{lo}, {hi}]; data years observed: "
            f"{int(years.min())}-{int(years.max())}"
        )
    result = data.isel({time_name: mask})
    # xarray's isel can promote serialisation metadata (e.g. 'calendar',
    # 'units') from encoding into attrs on the time coord, and downstream
    # pipeline steps (set_coordinates, attribute setters) may also add
    # `calendar` to attrs. Either way save_dataset then raises:
    #   ValueError: Key 'calendar' already exists in attrs on variable
    #     'time', and will not be overwritten.
    # Clear both attrs and encoding on the time coord; save_dataset will
    # re-infer them from the cftime values cleanly.
    if time_name in result.coords:
        result[time_name].attrs.clear()
        result[time_name].encoding.clear()
    return result


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

    # Year filter: pycmor's --year-start/--year-end CLI flags propagate
    # to rule.year_start / rule.year_end via core/overrides.py. LPJ-GUESS
    # .out files hold every year inline, so filtering at the dataframe
    # level here is the only way to keep cmorized output from leaking
    # non-requested years (cli57 emitted 152 monthly files per year of
    # source data). No-op when neither bound is set.
    _ys = getattr(rule, "year_start", None)
    _ye = getattr(rule, "year_end", None)
    if _ys is not None or _ye is not None:
        _lo = _ys if _ys is not None else int(df_all["Year"].min())
        _hi = _ye if _ye is not None else int(df_all["Year"].max())
        df_all = df_all[(df_all["Year"] >= _lo) & (df_all["Year"] <= _hi)].reset_index(drop=True)
        if df_all.empty:
            raise ValueError(f"LPJ-GUESS loader: no rows in [{_lo}, {_hi}] for rule {getattr(rule, 'name', '?')}")


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

    # Build time coordinate
    times = []
    for yr in years:
        for m in range(1, 13):
            times.append(cftime.DatetimeProlepticGregorian(int(yr), m, 15))

    # Allocate output array
    n_times = len(times)
    values = np.full((n_times, ncells), np.nan, dtype=np.float64)

    # Vectorized cell-index lookup via pandas merge. The earlier
    # df_all.iterrows() Python loop held the GIL for several minutes
    # at HR resolution, which prevented the dask worker thread from
    # heartbeating to its own LocalCluster scheduler — the scheduler
    # disconnected the worker after 30s, manifesting as
    # ``OSError: Timed out trying to connect to tcp://127.0.0.1:...``
    # in every cli3X veg_land run. Vectorizing drops the load from
    # minutes to seconds; the GIL is held only inside numpy C code.
    coords_df_with_idx = coords_df.copy()
    coords_df_with_idx["_cell_idx"] = np.arange(len(coords_df_with_idx))
    df_merged = df_all.merge(
        coords_df_with_idx[["Lon", "Lat", "_cell_idx"]], on=["Lon", "Lat"], how="left"
    )
    cell_idx_arr = df_merged["_cell_idx"].values
    valid = ~np.isnan(cell_idx_arr)
    cell_idx_int = cell_idx_arr[valid].astype(np.int64)
    yr_idx_arr = np.searchsorted(years, df_merged["Year"].values[valid])

    # Fill values — Jan..Dec columns ARE the monthly data for all LPJ-GUESS .out files
    model_variable = rule.get("model_variable", "Total")
    if is_pft_format:
        m_idx = df_merged["Mth"].values[valid].astype(np.int64) - 1
        t_idx_arr = yr_idx_arr * 12 + m_idx
        values[t_idx_arr, cell_idx_int] = df_merged["_total"].values[valid]
    else:
        # 12 monthly columns assigned per row → broadcast across months.
        for m_idx, month in enumerate(months):
            t_idx_arr = yr_idx_arr * 12 + m_idx
            values[t_idx_arr, cell_idx_int] = df_merged[month].values[valid]

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

    # Year filter: pycmor's --year-start/--year-end CLI flags propagate
    # to rule.year_start / rule.year_end via core/overrides.py. LPJ-GUESS
    # .out files hold every year inline, so filtering at the dataframe
    # level here is the only way to keep cmorized output from leaking
    # non-requested years (cli57 emitted 152 monthly files per year of
    # source data). No-op when neither bound is set.
    _ys = getattr(rule, "year_start", None)
    _ye = getattr(rule, "year_end", None)
    if _ys is not None or _ye is not None:
        _lo = _ys if _ys is not None else int(df_all["Year"].min())
        _hi = _ye if _ye is not None else int(df_all["Year"].max())
        df_all = df_all[(df_all["Year"] >= _lo) & (df_all["Year"] <= _hi)].reset_index(drop=True)
        if df_all.empty:
            raise ValueError(f"LPJ-GUESS loader: no rows in [{_lo}, {_hi}] for rule {getattr(rule, 'name', '?')}")

    years = np.sort(df_all["Year"].unique())

    # Build cell index
    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True]).reset_index(drop=True)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values
    ncells = len(coords_df)

    # Time coordinate: one per year (mid-year)
    times = [cftime.DatetimeProlepticGregorian(int(yr), 7, 1) for yr in years]

    model_variable = rule.get("model_variable", "Total")
    values = np.full((len(times), ncells), np.nan, dtype=np.float64)

    # Vectorized cell + year indexing. The earlier iterrows() Python
    # loop held the GIL long enough to break dask's LocalCluster
    # heartbeat (cf. load_lpjguess_monthly for the full rationale).
    coords_df_with_idx = coords_df.copy()
    coords_df_with_idx["_cell_idx"] = np.arange(len(coords_df_with_idx))
    df_merged = df_all.merge(
        coords_df_with_idx[["Lon", "Lat", "_cell_idx"]], on=["Lon", "Lat"], how="left"
    )
    cell_idx_arr = df_merged["_cell_idx"].values
    valid = ~np.isnan(cell_idx_arr)
    cell_idx_int = cell_idx_arr[valid].astype(np.int64)
    yr_idx_arr = np.searchsorted(years, df_merged["Year"].values[valid])
    values[yr_idx_arr, cell_idx_int] = df_merged[model_variable].values[valid]

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


def clip_small_negatives(data, rule):
    """
    Set values in [-threshold, +threshold] to zero.

    Clears tiny-negative numerical noise (~1e-12 to 1e-10) that the
    underlying model produces and that propagates through the pipeline
    untouched. Threshold defaults to 1e-10; override via rule.clip_threshold.

    Reviewer claim (Laszlo): for fNnetmin / fVegLitterMortality / fNloss /
    gpp / gppLut / mrtws / wetlandCH4, raw .out files already contain the
    same tiny-negative band — this is not a pycmor bug to chase upstream
    but to silence in the rule. LPJ-GUESS land variables have no legit
    signal below 1e-10, so this is safe to apply broadly.
    """
    threshold = float(rule.get("clip_threshold", 1e-10))
    for var_name in list(data.data_vars):
        da = data[var_name]
        data[var_name] = da.where((da > threshold) | (da < -threshold), 0.0)
    return data


def clip_floor_zero(data, rule):
    """
    Floor all values at zero (one-sided clip).

    Used for variables whose physical floor is 0 (soil moisture content,
    heterotrophic respiration efflux) but whose pycmor pipeline introduces
    negative values not present in the raw model output. Reviewer claim
    (Laszlo): for mrsol / rhSoil, raw .out has nneg == 0 but cmor has
    real negatives — the pycmor rule is introducing them and the cmor
    convention is non-negative.
    """
    for var_name in list(data.data_vars):
        da = data[var_name]
        data[var_name] = da.where(da >= 0.0, 0.0)
    return data


def broadcast_yearly_to_monthly(data, rule):
    """
    Broadcast a yearly LPJ-GUESS-loaded Dataset to monthly cadence.

    Each yearly sample is repeated 12 times with mid-month timestamps
    (day 15). Used for CMIP7 Emon variables whose authoritative source
    is the LPJ-GUESS yearly stand-area file (e.g. treeFrac_yearly.out):
    the native monthly file is LAI/phenology weighted and incorrectly
    imparts an annual cycle. See HANDOFF_d4_treeFrac_per_pft.md.
    """
    import cftime

    var_name = list(data.data_vars)[0]
    da = data[var_name]

    years = [int(t.year) for t in da.time.values]
    new_times = [
        cftime.DatetimeProlepticGregorian(yr, m, 15)
        for yr in years
        for m in range(1, 13)
    ]
    new_values = np.repeat(da.values, 12, axis=0)

    new_coords = {"time": new_times}
    for coord_name in ("lon", "lat"):
        if coord_name in da.coords:
            new_coords[coord_name] = da.coords[coord_name]

    new_da = xr.DataArray(
        new_values, dims=da.dims, coords=new_coords, name=var_name, attrs=da.attrs,
    )
    return new_da.to_dataset()


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

    # Year filter: pycmor's --year-start/--year-end CLI flags propagate
    # to rule.year_start / rule.year_end via core/overrides.py. LPJ-GUESS
    # .out files hold every year inline, so filtering at the dataframe
    # level here is the only way to keep cmorized output from leaking
    # non-requested years (cli57 emitted 152 monthly files per year of
    # source data). No-op when neither bound is set.
    _ys = getattr(rule, "year_start", None)
    _ye = getattr(rule, "year_end", None)
    if _ys is not None or _ye is not None:
        _lo = _ys if _ys is not None else int(df_all["Year"].min())
        _hi = _ye if _ye is not None else int(df_all["Year"].max())
        df_all = df_all[(df_all["Year"] >= _lo) & (df_all["Year"] <= _hi)].reset_index(drop=True)
        if df_all.empty:
            raise ValueError(f"LPJ-GUESS loader: no rows in [{_lo}, {_hi}] for rule {getattr(rule, 'name', '?')}")

    years = np.sort(df_all["Year"].unique())

    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True]).reset_index(drop=True)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values
    ncells = len(coords_df)

    times = [cftime.DatetimeProlepticGregorian(int(yr), 7, 1) for yr in years]

    model_variable = rule.get("model_variable", "psl")
    values = np.full((len(times), ncells), np.nan, dtype=np.float64)

    # Vectorized cell + year indexing (cf. load_lpjguess_monthly for rationale).
    coords_df_with_idx = coords_df.copy()
    coords_df_with_idx["_cell_idx"] = np.arange(len(coords_df_with_idx))
    df_merged = df_all.merge(
        coords_df_with_idx[["Lon", "Lat", "_cell_idx"]], on=["Lon", "Lat"], how="left"
    )
    cell_idx_arr = df_merged["_cell_idx"].values
    valid = ~np.isnan(cell_idx_arr)
    cell_idx_int = cell_idx_arr[valid].astype(np.int64)
    yr_idx_arr = np.searchsorted(years, df_merged["Year"].values[valid])
    values[yr_idx_arr, cell_idx_int] = df_merged[model_variable].values[valid]

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

    # Year filter: pycmor's --year-start/--year-end CLI flags propagate
    # to rule.year_start / rule.year_end via core/overrides.py. LPJ-GUESS
    # .out files hold every year inline, so filtering at the dataframe
    # level here is the only way to keep cmorized output from leaking
    # non-requested years (cli57 emitted 152 monthly files per year of
    # source data). No-op when neither bound is set.
    _ys = getattr(rule, "year_start", None)
    _ye = getattr(rule, "year_end", None)
    if _ys is not None or _ye is not None:
        _lo = _ys if _ys is not None else int(df_all["Year"].min())
        _hi = _ye if _ye is not None else int(df_all["Year"].max())
        df_all = df_all[(df_all["Year"] >= _lo) & (df_all["Year"] <= _hi)].reset_index(drop=True)
        if df_all.empty:
            raise ValueError(f"LPJ-GUESS loader: no rows in [{_lo}, {_hi}] for rule {getattr(rule, 'name', '?')}")

    years = np.sort(df_all["Year"].unique())

    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True]).reset_index(drop=True)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values
    ncells = len(coords_df)

    # Build time axis: one per (year, month)
    times = []
    for yr in years:
        for m in range(1, 13):
            times.append(cftime.DatetimeProlepticGregorian(int(yr), m, 15))

    model_variable = rule.get("model_variable", "psl")
    n_times = len(times)
    values = np.full((n_times, ncells), np.nan, dtype=np.float64)

    # Vectorized cell + (year, month) indexing (cf. load_lpjguess_monthly for rationale).
    coords_df_with_idx = coords_df.copy()
    coords_df_with_idx["_cell_idx"] = np.arange(len(coords_df_with_idx))
    df_merged = df_all.merge(
        coords_df_with_idx[["Lon", "Lat", "_cell_idx"]], on=["Lon", "Lat"], how="left"
    )
    cell_idx_arr = df_merged["_cell_idx"].values
    valid = ~np.isnan(cell_idx_arr)
    cell_idx_int = cell_idx_arr[valid].astype(np.int64)
    yr_idx_arr = np.searchsorted(years, df_merged["Year"].values[valid])
    m_idx_arr = df_merged["Mth"].values[valid].astype(np.int64) - 1
    t_idx_arr = yr_idx_arr * 12 + m_idx_arr
    values[t_idx_arr, cell_idx_int] = df_merged[model_variable].values[valid]

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

    Both inputs are 12-monthly OIFS-remapped FESOM fields with the same
    structure, but XIOS sometimes writes ``time_centered`` values that
    differ at the millisecond level between separate output files,
    which trips xarray's default ``join='exact'`` and raises
    ``AlignmentError``. Force coord-equality with ``join='override'``
    before the arithmetic so the time axis takes from ``sd``.
    """
    if isinstance(data, xr.Dataset):
        sd = data["sd"]
    else:
        sd = data
    rsn = _load_secondary_mf(rule, "second_input_path", "second_input_pattern", "second_variable")
    sd, rsn = xr.align(sd, rsn, join="override")

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

    # Year filter: pycmor's --year-start/--year-end CLI flags propagate
    # to rule.year_start / rule.year_end via core/overrides.py. LPJ-GUESS
    # .out files hold every year inline, so filtering at the dataframe
    # level here is the only way to keep cmorized output from leaking
    # non-requested years (cli57 emitted 152 monthly files per year of
    # source data). No-op when neither bound is set.
    _ys = getattr(rule, "year_start", None)
    _ye = getattr(rule, "year_end", None)
    if _ys is not None or _ye is not None:
        _lo = _ys if _ys is not None else int(df_all["Year"].min())
        _hi = _ye if _ye is not None else int(df_all["Year"].max())
        df_all = df_all[(df_all["Year"] >= _lo) & (df_all["Year"] <= _hi)].reset_index(drop=True)
        if df_all.empty:
            raise ValueError(f"LPJ-GUESS loader: no rows in [{_lo}, {_hi}] for rule {getattr(rule, 'name', '?')}")

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

    rtmt = rsdt - rsut - rlut

    where:
      rsdt = downwelling shortwave at TOA
      rsut = upwelling shortwave at TOA
      rlut = outgoing longwave at TOA (OLR)

    The earlier formula ``(rsdt - rsut) + (rlds - rlus)`` mixed TOA
    shortwave with surface longwave, which is not physically the TOA
    radiation balance. CMIP variable definition for ``rtmt`` is the
    standard TOA net flux given by the formula above. ``rlut`` is
    available in OIFS XIOS output (atmos_{day,mon}_rlut_*.nc).

    Primary input (data) should be a Dataset containing rsdt, rsut,
    and rlut from the monthly XIOS output.
    """
    rsdt = data["rsdt"]
    rsut = data["rsut"]
    rlut = data["rlut"]

    result = rsdt - rsut - rlut
    result.attrs = {
        "units": "W m-2",
        "standard_name": "net_downward_radiative_flux_at_top_of_atmosphere_model",
        "long_name": "Net Downward Radiative Flux at Top of Model",
    }
    result.name = rule.model_variable
    return result.to_dataset()


def regrid_oifs_to_fesom(data, rule):
    """
    Interpolate OIFS data from a reduced-Gaussian grid (flat 1D lat/lon
    where each (lat[i], lon[i]) is one node) onto FESOM unstructured nodes
    via nearest-neighbor on the unit sphere.

    Both source and target are unstructured — there is no rectilinear lat/lon
    intermediate. We build a KDTree on the source-grid Cartesian (x,y,z)
    points and query nearest-neighbor for each FESOM node. KDTree indices
    are cached via joblib (one set per (source-grid-id, mesh-id) pair) so
    repeated rules pay the build cost once.

    Suitable for smooth fields (radiation fluxes, sublimation, etc.). For
    fields with sharp gradients consider a barycentric/linear interpolant.

    Rule attributes:
      - grid_file: path to FESOM mesh.nc (required; contains 'lon'/'lat' node coords)
      - fesom_node_dim: name of node dimension in output (default: 'nod2')
      - regrid_cache_dir: dir to cache KDTree indices (optional)
    """
    from scipy.spatial import cKDTree as _cKDTree
    import hashlib
    import os.path as _osp
    import joblib as _joblib

    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("Rule must specify 'grid_file' for regrid_oifs_to_fesom")

    node_dim = rule.get("fesom_node_dim", "nod2")
    cache_dir = rule.get("regrid_cache_dir")

    mesh = xr.open_dataset(grid_file)
    fesom_lon = mesh[next(n for n in ("lon", "longitude") if n in mesh)].values
    fesom_lat = mesh[next(n for n in ("lat", "latitude") if n in mesh)].values
    mesh.close()

    src_lat = data.coords[next(n for n in ("lat", "latitude") if n in data.coords)].values
    src_lon = data.coords[next(n for n in ("lon", "longitude") if n in data.coords)].values
    if src_lat.shape != src_lon.shape:
        raise ValueError(
            f"regrid_oifs_to_fesom expects flat src lat/lon of equal length "
            f"(reduced-Gaussian style); got lat={src_lat.shape} lon={src_lon.shape}"
        )

    # Cartesian unit-sphere coords for KDTree (avoids longitude wrap pathology)
    def _to_xyz(lon_deg, lat_deg):
        lon = np.radians(lon_deg)
        lat = np.radians(lat_deg)
        return np.stack([np.cos(lat) * np.cos(lon),
                         np.cos(lat) * np.sin(lon),
                         np.sin(lat)], axis=-1)

    inds = None
    if cache_dir:
        key = hashlib.md5(
            (str(src_lat.shape) + str(grid_file) + f"{src_lat[0]:.4f}_{src_lat[-1]:.4f}").encode()
        ).hexdigest()
        cache_file = _osp.join(cache_dir, f"oifs_to_fesom_inds_{key}.joblib")
        if _osp.exists(cache_file):
            inds = _joblib.load(cache_file)
    if inds is None:
        tree = _cKDTree(_to_xyz(src_lon, src_lat))
        _, inds = tree.query(_to_xyz(fesom_lon, fesom_lat), k=1)
        if cache_dir:
            _os.makedirs(cache_dir, exist_ok=True)
            _joblib.dump(inds, cache_file)

    # OIFS-via-XIOS files use ``time_counter`` (and sometimes ``time_centered``)
    # rather than ``time``; accept any of the conventional names so callers
    # don't have to declare ``time_dimname:`` for every regrid rule.
    time_dim = next(
        (n for n in ("time", "time_counter", "time_centered", "valid_time", "t")
         if n in data.dims),
        None,
    )
    # Identify the source spatial dimension (the one we're gathering along).
    # OIFS XIOS uses ``cell``; older flatten-only paths might have ``ncells``.
    source_dim = next(
        (n for n in data.dims if n not in (time_dim,) and data.sizes[n] == src_lat.shape[0]),
        None,
    )
    if source_dim is None:
        # Fallback: use the trailing dim, the same axis the legacy
        # ``data.values[..., inds]`` indexed.
        source_dim = data.dims[-1]
    # Lazy gather via xarray-style fancy indexing — returns a dask-backed
    # DataArray when ``data`` is dask-backed (typical for load_mfdataset). The
    # earlier ``data.values[..., inds]`` materialised the full (T, N_fesom)
    # output up-front (~110 GB for hourly TCo319 → DARS 3.1M nodes), reliably
    # OOM-ing 16 GB workers. Streaming via isel keeps memory at one chunk's
    # worth.
    indexer = xr.DataArray(inds, dims=[node_dim])
    result = data.isel({source_dim: indexer})
    if time_dim is not None and time_dim in result.dims:
        result = result.transpose(time_dim, node_dim)
        # Force ``chunk({time: 1})`` after the regrid so downstream steps
        # (mask_where_no_seaice + timeavg + save_dataset) operate on
        # ~12 MB chunks instead of the inherited ~300 MB chunks. Without
        # this, two concurrent OIFS-regrid rules amplify chunk size
        # through ``where(mask)`` and timeavg accumulation buffers to
        # tens of GB per worker, OOM-ing the 256 GB cgroup. Per-timestep
        # chunking caps peak memory and stays dask-lazy (no algorithmic
        # change). cli26 lrcs_seaice_02 OOM motivated this.
        if hasattr(result, "chunks") and result.chunks is not None:
            result = result.chunk({time_dim: 1})
    result.name = data.name
    # ``isel`` preserves attrs, but be explicit in case of edge cases.
    if not result.attrs:
        result.attrs = dict(data.attrs)
    # The isel above drops the source-grid lat/lon coords (they were on
    # the now-removed ``source_dim``). Attach the FESOM target lat/lon
    # on the new node_dim so the written file has lat(nod2)/lon(nod2)
    # — matching the pure-FESOM hxy-si siblings (simass etc.) and the
    # CMIP7 ``dimensions: longitude latitude time`` requirement. Without
    # this, external tools (ushow, Panoply, ncview) can't render the
    # field, and per-file sanity-check maps fall back to the
    # _find_sibling_latlon workaround.
    result = result.assign_coords({
        "lat": (node_dim, fesom_lat),
        "lon": (node_dim, fesom_lon),
    })
    # Drop OIFS auxiliary time coords. XIOS files carry ``time_centered`` /
    # ``time_instant`` (plus their *_bounds twins) alongside the renamed
    # ``time`` (== old time_counter). Both reference dim ``time`` but with
    # different label values (HH:30 vs HH:00). Downstream xarray alignment
    # walks all coords sharing the dim and trips on the apparent duplicate
    # index. The legacy materialise-via-.values path implicitly dropped
    # them; the lazy-isel path preserves them, so we drop explicitly.
    for aux in ("time_centered", "time_instant",
                "time_centered_bounds", "time_instant_bounds",
                "time_counter_bounds", "time_bounds"):
        if aux in result.coords or aux in getattr(result, "variables", {}):
            result = result.drop_vars(aux, errors="ignore")
    return result


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
            (src_lat, src_lon),
            arr2d,
            method="linear",
            bounds_error=False,
            fill_value=np.nan,
        )
        return interp(query_pts).astype(np.float32)

    # Apply interpolation over time. Accept conventional time-dim aliases (XIOS
    # ``time_counter`` etc.) so the step doesn't silently broadcast against the
    # source grid when the rule omits ``time_dimname:``.
    time_dim = next(
        (n for n in ("time", "time_counter", "time_centered", "valid_time", "t")
         if n in data.dims),
        None,
    )
    if time_dim is None:
        result_np = _interp_timestep(data.values)
        result = xr.DataArray(result_np, dims=[node_dim], attrs=data.attrs)
    else:
        slices = [_interp_timestep(data.isel({time_dim: t}).values) for t in range(len(data[time_dim]))]
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

    Loads FESOM sea ice concentration via the standard path/pattern
    triplet and sets data values to NaN at all FESOM nodes where a_ice
    is zero, matching by time coordinate.

    Rule attributes:
      - aice_path: directory containing a_ice files
      - aice_pattern: regex matching FESOM a_ice filenames
        (e.g. ``a_ice\\.fesom\\..*\\.nc``)
      - aice_variable: variable name (default: 'a_ice')
      - fesom_node_dim: name of node dimension (default: 'nod2')
    """
    node_dim = rule.get("fesom_node_dim", "nod2")
    a_ice = _load_secondary_mf(rule, "aice_path", "aice_pattern", "aice_variable")

    # Align time coordinates: broadcast a_ice onto data's time grid via
    # nearest-neighbour. Use `reindex` rather than `sel`: `sel(..., method=
    # 'nearest')` keeps the *source*'s time values on the result, so
    # querying 8760 hourly timestamps against 365 daily a_ice rows produces
    # 8760 rows with the original 365 daily timestamps repeated 24x — i.e.
    # a_ice.time becomes non-unique, and the subsequent `data.where(mask)`
    # internal align fails with "(pandas) index has duplicate values".
    # Same mechanism collapses 12 monthly data + 12 sel'd-daily a_ice down
    # to 7 in the inner-join when the timestamps don't bit-match (sbl_seaice).
    # `reindex` rewrites the time coord to the requested values, so the
    # post-alignment a_ice.time is identical to data.time and `where` is a
    # no-op on the time axis. (DESIGN_PROPOSAL_recipe_failures_post_cli.md
    # §3.4 / §3.5: F4 + F5)
    time_dim = "time"
    if time_dim in data.dims and time_dim in a_ice.dims:
        a_ice = a_ice.reindex({time_dim: data[time_dim]}, method="nearest")
        # Match a_ice's time chunks to data's so the subsequent `where()` is
        # element-wise per chunk and stays dask-lazy. Without this, reindex
        # onto an 8760-hour grid produces a single big chunk for a_ice; when
        # `where` then broadcasts data (chunked) against a_ice (one chunk),
        # dask materializes an 8760 x N_nodes intermediate per worker — at
        # HR (3.15M nodes) that's ~100 GB across 9 concurrent F4 rules,
        # which spills, IO-contends on scratch, and live-locks all 4
        # workers. Chunk-matched `where` keeps peak ~chunk-sized.
        if hasattr(data, "chunks") and data.chunks is not None and time_dim in data.dims:
            time_idx = data.dims.index(time_dim)
            time_chunks = data.chunks[time_idx]
            if time_chunks:
                a_ice = a_ice.chunk({time_dim: time_chunks})

    # F4 instrumentation (DESIGN_PROPOSAL_recipe_failures_post_cli.md §3.4):
    # the duplicate-pandas-index error from data.where(mask) below has an
    # under-evidenced root cause hypothesis (OIFS aux time coords promoted
    # to indexes). Log indexes + uniqueness so the next run definitively
    # confirms or rejects. Drop these prints once F4 is closed.
    rule_name = rule.get("name", "?") if hasattr(rule, "get") else "?"
    try:
        data_t_unique = data[time_dim].to_index().is_unique if time_dim in data.coords else "no-coord"
        a_ice_t_unique = a_ice[time_dim].to_index().is_unique if time_dim in a_ice.coords else "no-coord"
        # Use logger.warning so it shows up in the user-facing log even with
        # the stdlib logging default WARNING level (custom_steps.py uses
        # stdlib `logging`, not loguru — INFO would be filtered).
        logger.warning(
            f"F4-INSTRUMENT mask_where_no_seaice [{rule_name}]: "
            f"data.indexes={list(data.indexes)} "
            f"data.coords={list(data.coords)} "
            f"data.{time_dim}.size={data.sizes.get(time_dim, '?')} "
            f"data.{time_dim}.is_unique={data_t_unique} "
            f"a_ice.{time_dim}.size={a_ice.sizes.get(time_dim, '?')} "
            f"a_ice.{time_dim}.is_unique={a_ice_t_unique}"
        )
    except Exception as _exc:
        logger.warning(f"F4-INSTRUMENT mask_where_no_seaice [{rule_name}]: instrumentation failed: {_exc}")

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
    "atlantic_arctic_ocean": (0, 3),  # atlantic + arctic
    "indian_pacific_ocean": (1, 2),  # pacific + indian
    "global_ocean": (0, 1, 2, 3, 4),  # all
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
        sub_lat = lat_idx[sel]  # (nsel,)
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
        "indian_pacific_ocean": "ipmoc",
        "global_ocean": "gmoc",
    }

    # Global 1° lat grid matching tripyview's integer-lat convention
    dlat = 1.0
    lat_centers = np.arange(-90.0, 90.0 + dlat, dlat)  # -90, -89, ..., 89, 90

    per_basin = {}
    for name, key in basin_to_key.items():
        moc = tpv.calc_zmoc(mesh, w, dlat=dlat, which_moc=key, diagpath=diagpath, do_info=False, do_compute=True)
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

    time_coord = data["time"].values if isinstance(data, xr.Dataset) and "time" in data.coords else np.arange(ntime)
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
        attrs={"units": "kg s-1", "long_name": "Ocean Meridional Overturning Mass Streamfunction"},
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
    # Force canonical dim order (time, nz, elem). FESOM 2.7 writes vtemp as
    # (time, elem, nz); transposing here keeps the per-timestep math below
    # (vt_t * weight_1d) shape-aligned regardless of the on-disk order.
    nz_dim = next((n for n in ("nz", "nz1", "lev", "depth") if n in vt.dims), None)
    elem_dim = next((n for n in ("elem", "ncells", "elem2D") if n in vt.dims), None)
    if nz_dim and elem_dim and "time" in vt.dims:
        vt = vt.transpose("time", nz_dim, elem_dim)
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


def _build_tripyview_mdiag(mesh, mesh_diag_path):
    """Translate native FESOM 2.x ``fesom.mesh.diag.nc`` into the variant
    `tripyview.sub_transp.calc_mhflx_box_fast_lessmem` expects.

    Maps the (4, edg_n) ``edge_cross_dxdy`` packed array (FESOM convention:
    [dx_l, dy_l, dx_r, dy_r], "distance from element centroid to edge mid"
    per gen_modules_diag.F90:1491) into the (2, edg_n) ``edge_dx_lr`` and
    ``edge_dy_lr`` tripyview expects, and derives ``edge_x``/``edge_y`` from
    ``edge_nodes`` plus the mesh node coordinates. Boundary edges where the
    second element is NaN get mapped to a -1 sentinel (tripyview masks those
    via ``edge_tri[1,:] < 0``).
    """
    raw = xr.open_dataset(mesh_diag_path)
    ecdx = raw["edge_cross_dxdy"].values
    edges_arr = (raw["edge_nodes"].values - 1).astype(np.int64)
    et_f = raw["edge_face_links"].values
    edge_tri = np.where(np.isfinite(et_f), et_f, 0).astype(np.int64) - 1
    raw.close()
    return xr.Dataset({
        "edge_x":     (("n2", "edg_n"),
                       np.stack([mesh.n_x[edges_arr[0]], mesh.n_x[edges_arr[1]]])),
        "edge_y":     (("n2", "edg_n"),
                       np.stack([mesh.n_y[edges_arr[0]], mesh.n_y[edges_arr[1]]])),
        "edge_dx_lr": (("n2", "edg_n"), np.stack([ecdx[0], ecdx[2]])),
        "edge_dy_lr": (("n2", "edg_n"), np.stack([ecdx[1], ecdx[3]])),
        "edge_tri":   (("n2", "edg_n"), edge_tri),
        "edges":      (("n2", "edg_n"), edges_arr),
    })


def compute_hfbasin_tripyview(data, rule):
    """Northward Ocean Heat Transport per basin via tripyview's edge-crossing
    integration. Replaces the per-element-area approximation in
    ``compute_hfbasin`` which violates discrete mass conservation (giving
    ±60 PW on HR FESOM vs Trenberth's ±2 PW).

    Uses tripyview's ``calc_mhflx_box_fast_lessmem`` (Scholz, FESOM/tripyview)
    which integrates the heat flux along the edges actually intersected by
    each latitude line — the path-integral discretisation Griffies / CMIP6
    require. Validation on Test_06_cli_y1587_v7 January 1587 gives Atlantic
    24.5°N = +1.26 PW, exactly matching RAPID (1.20 ± 0.12 PW).

    Rule attributes:
      - mesh_path: dir containing FESOM mesh files + ``fesom.mesh.diag.nc``
      - grid_file: path to mesh.nc (for depth_bnds → dz)
      - utemp_path / utemp_pattern / utemp_variable: secondary input for
        ``utemp.fesom.*.nc`` (needed in addition to ``vtemp``).

    Input ``data`` must be the Dataset loaded from the primary input pattern
    (``vtemp.fesom.*.nc``).

    Output: Dataset with ``hfbasin(time, basin, lat)`` in W, basin coord
    ``['atlantic_arctic_ocean', 'indian_pacific_ocean', 'global_ocean']``.
    """
    import os as _os
    import tripyview as _tpv
    import shapefile as _shp

    mesh_path = rule.get("mesh_path")
    if mesh_path is None:
        raise ValueError("compute_hfbasin_tripyview requires 'mesh_path' (FESOM mesh directory)")
    grid_file = rule.get("grid_file") or _os.path.join(mesh_path, "mesh.nc")
    mesh_diag_path = _os.path.join(mesh_path, "fesom.mesh.diag.nc")
    if not _os.path.exists(mesh_diag_path):
        raise FileNotFoundError(f"compute_hfbasin_tripyview needs fesom.mesh.diag.nc at {mesh_diag_path}")

    mesh = _tpv.load_mesh_fesom2(mesh_path, do_pickle=True, do_info=False)
    mdiag = _build_tripyview_mdiag(mesh, mesh_diag_path)

    # Primary input: vtemp (or utemp/vtemp combined)
    if isinstance(data, xr.Dataset) and "vtemp" in data.data_vars:
        v_da = data["vtemp"]
    else:
        v_da = data if not isinstance(data, xr.Dataset) else data[list(data.data_vars)[0]]

    # Secondary input: utemp
    ut_da = _load_secondary_mf(rule, "utemp_path", "utemp_pattern", "utemp_variable")

    # Layer thickness from mesh.nc
    m = xr.open_dataset(grid_file)
    nz1 = v_da.sizes.get("nz") or v_da.sizes.get("nz1")
    if nz1 is None:
        raise ValueError(f"vtemp has no nz/nz1 dimension; dims={v_da.dims}")
    dz = np.diff(m["depth_bnds"].values)[:nz1].astype(np.float64)
    m.close()

    # Rename nz->nz1 to match tripyview convention. Tripyview's
    # sub_transp.py:526 does ``data_latbin[vnameu][1, mask, :] = 0`` —
    # in-place numpy assignment which breaks on lazy dask arrays. So
    # the data passed to ``calc_mhflx_box_fast_lessmem`` must be eager.
    # We used to ``.load()`` the full vtemp+utemp here (24 GB for HR
    # monthly), which left the worker oscillating at the 75% pause
    # threshold for the whole loop. Per-timestep ``.load()`` inside
    # the loop caps peak input memory at ~2 GB instead.
    if "nz" in v_da.dims:
        v_da = v_da.rename({"nz": "nz1"})
    if "nz" in ut_da.dims:
        ut_da = ut_da.rename({"nz": "nz1"})

    # CMIP basin definitions: atlantic_arctic, indo-pacific, global.
    # tripyview ships Atlantic_MOC and IndoPacific_MOC shapefiles whose
    # boundaries follow the CMIP6 AWI-CM publication.
    shp_dir = rule.get("basin_shapefile_dir") or _os.path.join(
        _os.path.dirname(_tpv.__file__), "shapefiles", "moc_basins"
    )
    basins = [
        ("atlantic_arctic_ocean", _shp.Reader(_os.path.join(shp_dir, "Atlantic_MOC.shp"))),
        ("indian_pacific_ocean",  _shp.Reader(_os.path.join(shp_dir, "IndoPacific_MOC.shp"))),
        ("global_ocean",          "global"),
    ]

    # Loop over time explicitly: tripyview's sum_over_latbin indexes data via
    # ``data_latbin[vnameu][1, mask, :] = 0`` (sub_transp.py:526) which
    # only works when no time dim is present in `data` (or time>1 and the
    # caller handles it). Looping per-timestep is cleanest and matches the
    # validated POC.
    has_time = "time" in v_da.dims
    if has_time:
        time_vals = v_da["time"].values
        ntime = v_da.sizes["time"]
    else:
        time_vals = None
        ntime = 1

    # Pre-build per-basin output arrays
    per_basin_results = {n: [] for n, _ in basins}
    glob_lat = None
    for t in range(ntime):
        # Eager-load only the current timestep — 2 GB peak instead of 24 GB.
        if has_time:
            v_t = v_da.isel(time=t).load()
            ut_t = ut_da.isel(time=t).load()
        else:
            v_t = v_da.load()
            ut_t = ut_da.load()
        packed = xr.Dataset({"u": ut_t, "v": v_t})
        packed["dz"] = (("nz1",), dz)
        packed.attrs["proj"] = "index+xy"
        if "nz1" in packed.coords:
            packed = packed.drop_vars("nz1")
        for name, box in basins:
            out_list = _tpv.sub_transp.calc_mhflx_box_fast_lessmem(
                mesh, packed, None, mdiag, [box], dlat=1.0,
                do_info=False, do_load=True,
            )
            out = out_list[0]
            if glob_lat is None and name == "global_ocean":
                glob_lat = out["lat"].values
            per_basin_results[name].append(out)
        # Release this iteration's loaded data before the next loop.
        del v_t, ut_t, packed

    if glob_lat is None:
        # safety: if global wasn't iterated yet, pull from first basin
        glob_lat = per_basin_results[basins[0][0]][0]["lat"].values

    # Stack: (time, basin, lat) in W
    if has_time:
        stacked = np.full((ntime, 3, glob_lat.size), np.nan, dtype=np.float64)
    else:
        stacked = np.full((3, glob_lat.size), np.nan, dtype=np.float64)

    basin_names = [n for n, _ in basins]
    for bi, name in enumerate(basin_names):
        for t, out in enumerate(per_basin_results[name]):
            mh = out["mhflx"].reindex(lat=glob_lat, fill_value=0.0) * 1.0e15
            if has_time:
                stacked[t, bi, :] = mh.values
            else:
                stacked[bi, :] = mh.values

    if has_time:
        coords = {"time": time_vals, "basin": basin_names, "lat": glob_lat}
        dims = ("time", "basin", "lat")
    else:
        coords = {"basin": basin_names, "lat": glob_lat}
        dims = ("basin", "lat")

    hfbasin = xr.DataArray(
        stacked,
        dims=dims, coords=coords,
        name=rule.model_variable,
        attrs={
            "units": "W",
            "standard_name": "northward_ocean_heat_transport",
            "long_name": "Northward Ocean Heat Transport",
            "cell_methods": "longitude: sum (comment: basin sum [along zig-zag grid path]) depth: sum time: mean",
            "comment": "Edge-crossing integration via tripyview "
                       "(calc_mhflx_box_fast_lessmem). Replaces the broken "
                       "per-element-area approximation; see "
                       "tools/sanity_check/reports/hfbasin_research_plan.md.",
        },
    )
    # Attach CF attrs to the lat coord so the written file has a usable
    # coordinate variable (was previously a bare numeric coord — cli37
    # review: "flawed coordinate variable").
    hfbasin["lat"].attrs.update({
        "standard_name": "latitude",
        "long_name": "Latitude",
        "units": "degrees_north",
        "axis": "Y",
    })
    return hfbasin.to_dataset()


def compute_sltbasin_tripyview(data, rule):
    """Northward Ocean Salt Transport per basin via tripyview's edge-crossing
    integration. Sibling of ``compute_hfbasin_tripyview``; replaces
    ``compute_sltbasin`` which used the same per-element-area approximation
    that gave ±60 PW on hfbasin (here it gave ±45 GgN/s on sltbasin).

    FESOM emits ``usalt``/``vsalt`` = v·S (m/s × psu), analogous to
    ``utemp``/``vtemp`` = v·T (m/s × degC) — same edge-crossing physics,
    different scalar field. We reuse tripyview's
    ``calc_mhflx_box_fast_lessmem`` with usalt/vsalt as the u/v inputs,
    then post-process to land in CMIP ``kg s-1``:

      tripyview output (using salt as if it were heat):
        Q_PW = rho0 * cp * 1e-15 * (-1) * ∫∫ vsalt·dz·dx

      we want CMIP sltbasin:
        Q_kg_s = rho0 * 1e-3 * ∫∫ vsalt·dz·dx        (psu → mass fraction)

      ratio: Q_kg_s / Q_PW = -1e-3 / (cp * 1e-15) = -1e+12 / 3850
                            ≈ -2.5974e+8 kg/s per PW

    Rule attributes:
      - mesh_path: dir containing FESOM mesh + ``fesom.mesh.diag.nc``
      - grid_file: path to mesh.nc (for depth_bnds)
      - usalt_path / usalt_pattern / usalt_variable: secondary input

    Primary input ``data`` is the Dataset from the ``vsalt.fesom.*.nc``
    pattern.

    Output: Dataset with ``sltbasin(time, basin, lat)`` in kg s-1, basin
    coord ``['atlantic_arctic_ocean', 'indian_pacific_ocean', 'global_ocean']``.

    See PLAN/research at tools/sanity_check/reports/hfbasin_research_plan.md
    for the underlying tripyview/Griffies path-integral discretisation.
    """
    import os as _os
    import tripyview as _tpv
    import shapefile as _shp

    mesh_path = rule.get("mesh_path")
    if mesh_path is None:
        raise ValueError("compute_sltbasin_tripyview requires 'mesh_path'")
    grid_file = rule.get("grid_file") or _os.path.join(mesh_path, "mesh.nc")
    mesh_diag_path = _os.path.join(mesh_path, "fesom.mesh.diag.nc")
    if not _os.path.exists(mesh_diag_path):
        raise FileNotFoundError(
            f"compute_sltbasin_tripyview needs fesom.mesh.diag.nc at {mesh_diag_path}"
        )

    mesh = _tpv.load_mesh_fesom2(mesh_path, do_pickle=True, do_info=False)
    mdiag = _build_tripyview_mdiag(mesh, mesh_diag_path)

    # Primary input: vsalt
    if isinstance(data, xr.Dataset) and "vsalt" in data.data_vars:
        v_da = data["vsalt"]
    else:
        v_da = data if not isinstance(data, xr.Dataset) else data[list(data.data_vars)[0]]

    # Secondary input: usalt
    ut_da = _load_secondary_mf(rule, "usalt_path", "usalt_pattern", "usalt_variable")

    m = xr.open_dataset(grid_file)
    nz1 = v_da.sizes.get("nz") or v_da.sizes.get("nz1")
    if nz1 is None:
        raise ValueError(f"vsalt has no nz/nz1 dimension; dims={v_da.dims}")
    dz = np.diff(m["depth_bnds"].values)[:nz1].astype(np.float64)
    m.close()

    # Per-timestep eager load (mirror of compute_hfbasin_tripyview fix):
    # full vsalt+usalt is 24 GB for HR monthly; loading all at once made
    # the worker oscillate at the 75% pause threshold. Per-iteration
    # ``.load()`` caps peak input memory at ~2 GB.
    if "nz" in v_da.dims:
        v_da = v_da.rename({"nz": "nz1"})
    if "nz" in ut_da.dims:
        ut_da = ut_da.rename({"nz": "nz1"})

    shp_dir = rule.get("basin_shapefile_dir") or _os.path.join(
        _os.path.dirname(_tpv.__file__), "shapefiles", "moc_basins"
    )
    basins = [
        ("atlantic_arctic_ocean", _shp.Reader(_os.path.join(shp_dir, "Atlantic_MOC.shp"))),
        ("indian_pacific_ocean",  _shp.Reader(_os.path.join(shp_dir, "IndoPacific_MOC.shp"))),
        ("global_ocean",          "global"),
    ]

    has_time = "time" in v_da.dims
    if has_time:
        time_vals = v_da["time"].values
        ntime = v_da.sizes["time"]
    else:
        time_vals = None
        ntime = 1

    per_basin_results = {n: [] for n, _ in basins}
    glob_lat = None
    for t in range(ntime):
        if has_time:
            v_t = v_da.isel(time=t).load()
            ut_t = ut_da.isel(time=t).load()
        else:
            v_t = v_da.load()
            ut_t = ut_da.load()
        packed = xr.Dataset({"u": ut_t, "v": v_t})
        packed["dz"] = (("nz1",), dz)
        packed.attrs["proj"] = "index+xy"
        if "nz1" in packed.coords:
            packed = packed.drop_vars("nz1")
        for name, box in basins:
            out_list = _tpv.sub_transp.calc_mhflx_box_fast_lessmem(
                mesh, packed, None, mdiag, [box], dlat=1.0,
                do_info=False, do_load=True,
            )
            out = out_list[0]
            if glob_lat is None and name == "global_ocean":
                glob_lat = out["lat"].values
            per_basin_results[name].append(out)
        del v_t, ut_t, packed

    if glob_lat is None:
        glob_lat = per_basin_results[basins[0][0]][0]["lat"].values

    # Post-process: tripyview returned PW-as-if-heat. Convert to kg/s salt.
    # See docstring for the derivation: factor = -1e+12 / cp = -2.5974e+8.
    _CP = 3850.0
    factor = -1e+12 / _CP

    if has_time:
        stacked = np.full((ntime, 3, glob_lat.size), np.nan, dtype=np.float64)
    else:
        stacked = np.full((3, glob_lat.size), np.nan, dtype=np.float64)

    basin_names = [n for n, _ in basins]
    for bi, name in enumerate(basin_names):
        for t, out in enumerate(per_basin_results[name]):
            mh = out["mhflx"].reindex(lat=glob_lat, fill_value=0.0) * factor
            if has_time:
                stacked[t, bi, :] = mh.values
            else:
                stacked[bi, :] = mh.values

    if has_time:
        coords = {"time": time_vals, "basin": basin_names, "lat": glob_lat}
        dims = ("time", "basin", "lat")
    else:
        coords = {"basin": basin_names, "lat": glob_lat}
        dims = ("basin", "lat")

    sltbasin = xr.DataArray(
        stacked,
        dims=dims, coords=coords,
        name=rule.model_variable,
        attrs={
            "units": "kg s-1",
            "standard_name": "northward_ocean_salt_transport",
            "long_name": "Northward Ocean Salt Transport",
            "cell_methods": "longitude: sum (comment: basin sum [along zig-zag grid path]) depth: sum time: mean",
            "comment": "Edge-crossing integration via tripyview "
                       "(calc_mhflx_box_fast_lessmem with vsalt/usalt). "
                       "Replaces the broken per-element-area approximation; "
                       "see tools/sanity_check/reports/hfbasin_research_plan.md.",
        },
    )
    sltbasin["lat"].attrs.update({
        "standard_name": "latitude",
        "long_name": "Latitude",
        "units": "degrees_north",
        "axis": "Y",
    })
    return sltbasin.to_dataset()


def compute_sltbasin(data, rule):
    """Northward ocean salt transport by basin (CMIP sltbasin), kg s-1.

    Same structure as compute_hfbasin but using usalt/vsalt = v·S (g/kg·m/s).
    Output: ρ₀ · Σ_elems vsalt · dz · edge  [g/s], scaled to kg/s.
    """
    grid_file = rule.get("grid_file")
    if grid_file is None:
        raise ValueError("compute_sltbasin requires 'grid_file'")
    vs = data["vsalt"] if isinstance(data, xr.Dataset) and "vsalt" in data else data
    # Same canonical-order transpose as compute_hfbasin — FESOM writes
    # (time, elem, nz); the math below assumes (time, nz, elem).
    nz_dim = next((n for n in ("nz", "nz1", "lev", "depth") if n in vs.dims), None)
    elem_dim = next((n for n in ("elem", "ncells", "elem2D") if n in vs.dims), None)
    if nz_dim and elem_dim and "time" in vs.dims:
        vs = vs.transpose("time", nz_dim, elem_dim)
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


# Default sigma2 density bins from FESOM 2.7 (gen_modules_diag.F90:55-66).
# 89 levels, finer resolution around dense water classes. Override via the
# rule attribute ``std_dens`` if your FESOM version uses a different array.
_FESOM2_STD_DENS = np.array(
    [
        0.0,
        30.0,
        30.55556,
        31.11111,
        31.36,
        31.66667,
        31.91,
        32.22222,
        32.46,
        32.77778,
        33.01,
        33.33333,
        33.56,
        33.88889,
        34.11,
        34.44444,
        34.62,
        35.00000,
        35.05,
        35.10622,
        35.20319,
        35.29239,
        35.37498,
        35.41300,
        35.45187,
        35.52380,
        35.59136,
        35.65506,
        35.71531,
        35.77247,
        35.82685,
        35.87869,
        35.92823,
        35.97566,
        35.98,
        36.02115,
        36.06487,
        36.10692,
        36.14746,
        36.18656,
        36.22434,
        36.26089,
        36.29626,
        36.33056,
        36.36383,
        36.39613,
        36.42753,
        36.45806,
        36.48778,
        36.51674,
        36.54495,
        36.57246,
        36.59500,
        36.59932,
        36.62555,
        36.65117,
        36.67621,
        36.68000,
        36.70071,
        36.72467,
        36.74813,
        36.75200,
        36.77111,
        36.79363,
        36.81570,
        36.83733,
        36.85857,
        36.87500,
        36.87940,
        36.89985,
        36.91993,
        36.93965,
        36.95904,
        36.97808,
        36.99682,
        37.01524,
        37.03336,
        37.05119,
        37.06874,
        37.08602,
        37.10303,
        37.11979,
        37.13630,
        37.15257,
        37.16861,
        37.18441,
        37.50000,
        37.75000,
        40.00000,
    ],
    dtype=np.float64,
)


def _zmoc_basin_loop(mesh, w, diagpath):
    """Run tpv.calc_zmoc for the three CMIP basins; return dict basin → ψ DataArray (Sv)."""
    import tripyview as tpv

    basin_to_key = {
        "atlantic_arctic_ocean": "aamoc",
        "indian_pacific_ocean": "ipmoc",
        "global_ocean": "gmoc",
    }
    out = {}
    for name, key in basin_to_key.items():
        moc = tpv.calc_zmoc(
            mesh,
            w,
            dlat=1.0,
            which_moc=key,
            diagpath=diagpath,
            do_info=False,
            do_compute=True,
        )
        out[name] = moc["zmoc"]
    return out


def _align_zmoc_to_cmip(per_basin, mesh, time_coord_source):
    """Pack per-basin ψ(time, nz, lat) onto a CMIP (time, lev, basin, lat) grid.

    Returns DataArray (in Sv — caller multiplies by 1e9 for kg/s).
    """
    first = next(iter(per_basin.values()))
    has_time = "time" in first.dims
    zdim = "nz" if "nz" in first.dims else ("nz1" if "nz1" in first.dims else None)
    if zdim is None:
        raise ValueError(f"zmoc has no vertical dim (dims={first.dims})")
    nz = first.sizes[zdim]
    ntime = first.sizes["time"] if has_time else 1
    lev = np.asarray(mesh.zlev[:nz])

    dlat = 1.0
    lat_centers = np.arange(-90.0, 90.0 + dlat, dlat)
    out = np.full((ntime, nz, 3, lat_centers.size), np.nan, dtype=np.float64)
    for j, name in enumerate(_CMIP_BASIN_NAMES):
        da = per_basin[name].reindex(lat=lat_centers)
        vals = np.asarray(da.values)
        if vals.ndim == 2:
            out[0, :, j, :] = vals
        else:
            out[:, :, j, :] = vals

    if has_time and "time" in first.coords:
        time_coord = first["time"].values
    elif isinstance(time_coord_source, xr.Dataset) and "time" in time_coord_source.coords:
        time_coord = time_coord_source["time"].values
    else:
        time_coord = np.arange(ntime)
    if not has_time and ntime == 1 and isinstance(time_coord, np.ndarray) and time_coord.size != 1:
        time_coord = time_coord[:1]

    return xr.DataArray(
        out,
        dims=("time", "lev", "basin", "lat"),
        coords={"time": time_coord, "lev": lev, "basin": list(_CMIP_BASIN_NAMES), "lat": lat_centers},
    )


def _align_v_w_for_zmoc(w, mesh, diagpath):
    """Apply the same lat/lon-coord and vertical-dim alignment that compute_msftmz uses."""
    if "time" not in w.dims:
        w = w.expand_dims("time")
    w = w.load()
    w = w.assign_coords(lat=("nod2", mesh.n_y), lon=("nod2", mesh.n_x))
    try:
        if _os.path.isfile(diagpath):
            with xr.open_dataset(diagpath) as _diag:
                _na_dims = set(_diag["nod_area"].dims)
            _diag_vdim = None
            for _src, _dst in (("nl", "nz"), ("nl1", "nz1"), ("nz", "nz"), ("nz1", "nz1")):
                if _src in _na_dims:
                    _diag_vdim = _dst
                    break
            if _diag_vdim is not None:
                for _wv in ("nz", "nz1"):
                    if _wv in w.dims and _wv != _diag_vdim:
                        w = w.rename({_wv: _diag_vdim})
                        break
    except Exception:
        pass
    return w


def compute_msftmmpa_depth(data, rule):
    """
    Ocean meridional overturning mass streamfunction due to parameterized
    mesoscale advection, depth-space (CMIP msftmmpa with branding
    tavg-ol-hyb-sea, a.k.a. msftmzmpa), kg s-1.

    Mirrors :func:`compute_msftmz` but feeds FESOM's vertical *bolus*
    velocity (``bolus_w``, GM scheme) into tripyview's calc_zmoc. The bolus
    streamfunction is exactly the contribution of parameterized mesoscale
    advection to the depth-space MOC.

    Inputs:
      data: xr.Dataset with 'bolus_w' (time, nz, nod2). Loaded by
            ``pycmor.core.gather_inputs.load_mfdataset`` from
            ``bolus_w.fesom.*.nc``.
      rule.mesh_path: FESOM mesh directory.
      rule.diag_file (optional): path to fesom.mesh.diag.nc.
    Output: DataArray (time, lev, basin, lat) in kg s-1.
    """
    import tripyview as tpv

    mesh_path = rule.get("mesh_path")
    if mesh_path is None:
        raise ValueError("compute_msftmmpa_depth requires 'mesh_path'")
    diagpath = rule.get("diag_file", f"{mesh_path}/fesom.mesh.diag.nc")

    mesh = tpv.load_mesh_fesom2(mesh_path, do_info=False)
    if isinstance(data, xr.Dataset):
        if "bolus_w" not in data.data_vars:
            raise ValueError(f"compute_msftmmpa_depth expects 'bolus_w' in data; got {list(data.data_vars)}")
        w = data[["bolus_w"]].rename({"bolus_w": "w"})
    else:
        w = data.to_dataset().rename({data.name: "w"})

    w = _align_v_w_for_zmoc(w, mesh, diagpath)
    per_basin = _zmoc_basin_loop(mesh, w, diagpath)
    da_sv = _align_zmoc_to_cmip(per_basin, mesh, time_coord_source=data)
    da_out = (
        (da_sv * 1.0e9)
        .rename(rule.model_variable)
        .assign_attrs(
            units="kg s-1",
            long_name="Ocean Meridional Overturning Mass Streamfunction Due to Parameterized Mesoscale Advection",
        )
    )
    return da_out.to_dataset()


def _open_fesom_year_files(data_path, vname, years=None):
    """Open <vname>.fesom.YYYY.nc files (optionally year-filtered) into one Dataset.

    Returns ``None`` if no files match (so the caller can decide whether the
    absence is fatal).
    """
    pat = _re.compile(rf"{_re.escape(vname)}\.fesom\.(\d{{4}})\.nc$")
    paths = []
    for fn in sorted(_os.listdir(data_path)):
        m = pat.match(fn)
        if m and (years is None or int(m.group(1)) in years):
            paths.append(_os.path.join(data_path, fn))
    if not paths:
        return None
    return xr.open_mfdataset(
        paths,
        combine="by_coords",
        parallel=False,
        decode_times=True,
        use_cftime=True,
        chunks={"time": 1},
    )


def _msftm_density_streamfunction(div_da, lat_nodes, basin_nodes):
    """Bin density-class divergence → ψ(time, dens, basin, lat).

    Accepts ``div_da`` with dims that include ``time`` (optional), ``ndens``,
    and ``nod2`` in any order. Cumulative sum is taken N→S over lat. Returns
    volume streamfunction (m³/s) on (ntime, ndens, 3, nlat). Caller scales to mass.

    Implementation: per time step, scatter (ndens × nod2) values into
    (ndens × nbasin × nlat) bins via a single ``np.bincount`` — orders of
    magnitude faster than per-basin ``np.add.at`` for HR-mesh-sized inputs.
    """
    has_time = "time" in div_da.dims
    target_dims = (("time",) if has_time else ()) + ("ndens", "nod2")
    div_da = div_da.transpose(*target_dims)

    ntime = div_da.sizes.get("time", 1)
    ndens_n = div_da.sizes["ndens"]
    lat_edges = _lat_edges(1.0)
    lat_centers = 0.5 * (lat_edges[:-1] + lat_edges[1:])
    nlat = lat_centers.size
    basin_ids = _BASIN_IDS
    nb = len(basin_ids)

    # Precompute per-node bin index in a flat (basin × lat) space; -1 for nodes
    # outside any tracked basin.
    lat_idx_all = np.clip(np.searchsorted(lat_edges, lat_nodes, side="right") - 1, 0, nlat - 1)
    bin_idx = np.full(lat_nodes.size, -1, dtype=np.int64)
    for bi, bid in enumerate(basin_ids):
        sel = basin_nodes == bid
        bin_idx[sel] = bi * nlat + lat_idx_all[sel]
    valid = bin_idx >= 0
    bin_idx_v = bin_idx[valid]
    nvalid = bin_idx_v.size
    nbins5 = nb * nlat

    # Full (ndens, nvalid) flat-bin index: dens-stride is nbins5.
    dens_offset = (np.arange(ndens_n, dtype=np.int64) * nbins5)[:, None]
    flat_idx = (dens_offset + bin_idx_v[None, :]).ravel()

    binned3_all = np.zeros((ntime, ndens_n, 3, nlat), dtype=np.float64)
    for t in range(ntime):
        slab = (div_da.isel(time=t).values if has_time else div_da.values)  # (ndens, nod2)
        slab_v = slab[:, valid]
        slab_v = np.where(np.isfinite(slab_v), slab_v, 0.0).astype(np.float64)
        binned = np.bincount(flat_idx, weights=slab_v.ravel(), minlength=ndens_n * nbins5)
        binned5_t = binned.reshape(ndens_n, nb, nlat)
        binned3_all[t] = _aggregate_to_cmip_basins(binned5_t, lat_centers)

    # Per-class meridional flux at latitude j: ψ_class(ρ_c, j) = -Σ_{φ' ≥ φ} divergence
    # (Gauss: cumsum N→S of horizontal divergence gives north flux at φ with this sign.)
    psi_class = -np.flip(np.flip(binned3_all, axis=-1).cumsum(axis=-1), axis=-1)

    # CMIP msftmrho convention: streamfunction is the cumulative integral over
    # density. Match tripyview's calc_dmoc orientation — cumsum from densest to
    # lightest (so ψ at ρ_max = ψ_class(ρ_max), ψ at ρ_min = total ≈ 0 by mass
    # conservation). For a typical AMOC this gives ψ_max > 0 at the NADW
    # interface (representing the upper-limb northward transport above ρ_c).
    psi = np.flip(np.flip(psi_class, axis=-3).cumsum(axis=-3), axis=-3)
    return psi, lat_centers


def _normalize_dmoc_dim(da):
    """Rename schema-variant dimension names to a canonical ('time', 'ndens', 'nod2')."""
    rename = {}
    if "std_dens" in da.dims:
        rename["std_dens"] = "ndens"
    if rename:
        da = da.rename(rename)
    return da


def _resolve_rho_axis(div_da, rule_std_dens):
    """Pick the rho coordinate values from rule.std_dens, then file coord, then default."""
    if rule_std_dens is not None:
        return np.asarray(rule_std_dens, dtype=np.float64)
    for coord_name in ("std_dens", "ndens"):
        if coord_name in div_da.coords:
            vals = np.asarray(div_da[coord_name].values)
            if np.issubdtype(vals.dtype, np.floating):
                return vals.astype(np.float64)
    return _FESOM2_STD_DENS.copy()


def compute_msftm_density(data, rule):
    """
    Ocean meridional overturning mass streamfunction in density space
    (CMIP msftm with branding tavg-rho-hyb-sea, a.k.a. msftmrho), kg s-1.

    Total advective transport: cumulative-summed (lat) integrated divergence
    of the resolved velocity (FESOM ``std_dens_DIV``), plus the GM bolus
    contribution (``std_dens_DIVbolus``) when present in ``data_path``.
    No-bolus configurations (HR with ``Fer_GM=.false.``) work too — bolus
    files are detected at runtime and skipped silently if absent.

    Pipeline shape: prepend ``pycmor.core.gather_inputs.load_mfdataset`` so
    pycmor handles year-filtering of the primary ``std_dens_DIV`` files via
    the rule's input pattern. The bolus addend (``std_dens_DIVbolus``) is
    discovered in ``data_path`` using the year range of the loaded data.

    Required rule attributes:
      data_path: FESOM output directory
      mesh_path: directory holding mesh.nc (or full mesh.nc path)
      basin_mask_file: path to basin_mask.nc with ``basin`` (per-node id)

    Output: DataArray (time, rho, basin, lat) in kg s-1.
    """
    if not isinstance(data, xr.Dataset) or "std_dens_DIV" not in data.data_vars:
        raise ValueError(
            "compute_msftm_density expects 'std_dens_DIV' in input data; got "
            f"{list(data.data_vars) if isinstance(data, xr.Dataset) else type(data)}"
        )
    div = _normalize_dmoc_dim(data["std_dens_DIV"])  # (time, ndens, nod2)

    data_path = rule.get("data_path")
    mesh_path = rule.get("mesh_path")
    basin_mask_file = rule.get("basin_mask_file")
    if not all([data_path, mesh_path, basin_mask_file]):
        raise ValueError("compute_msftm_density requires 'data_path', 'mesh_path', 'basin_mask_file' on the rule")

    # Add GM bolus divergence if available, matched on the resolved div's year range.
    if "time" in div.coords:
        years = sorted({int(t.year) for t in div["time"].values}) if div.sizes.get("time", 0) else None
    else:
        years = None
    bolus_ds = _open_fesom_year_files(data_path, "std_dens_DIVbolus", years)
    if bolus_ds is not None:
        bolus = _normalize_dmoc_dim(bolus_ds["std_dens_DIVbolus"])
        # align on time/ndens; sum into resolved
        div = div + bolus.reindex_like(div, method=None)

    # Mesh + basin info
    grid_file = mesh_path if _os.path.isfile(mesh_path) else _os.path.join(mesh_path, "mesh.nc")
    with xr.open_dataset(grid_file) as m:
        lat_nodes = m["lat"].values
    with xr.open_dataset(basin_mask_file) as bm:
        basin_nodes = bm["basin"].values

    psi, lat_centers = _msftm_density_streamfunction(div, lat_nodes, basin_nodes)
    psi_kg = psi * _RHO0  # m³/s × kg/m³ → kg/s

    rho_coord = _resolve_rho_axis(div, rule.get("std_dens"))
    time_coord = div["time"].values if "time" in div.coords else np.arange(psi_kg.shape[0])

    da_out = xr.DataArray(
        psi_kg,
        dims=("time", "rho", "basin", "lat"),
        coords={
            "time": time_coord,
            "rho": rho_coord,
            "basin": list(_CMIP_BASIN_NAMES),
            "lat": lat_centers,
        },
        name=rule.model_variable,
        attrs={
            "units": "kg s-1",
            "long_name": "Ocean Meridional Overturning Mass Streamfunction",
        },
    )
    return da_out.to_dataset()


def compute_msftmmpa_density(data, rule):
    """
    Ocean meridional overturning mass streamfunction due to parameterized
    mesoscale advection in density space (CMIP msftmmpa with branding
    tavg-rho-hyb-sea, a.k.a. msftmrhompa), kg s-1.

    Bolus-only contribution: identical pipeline to :func:`compute_msftm_density`
    but driven by ``std_dens_DIVbolus`` (GM bolus density-class divergence).
    Only run when ``Fer_GM=.true.`` produced bolus output; otherwise the
    rule's input pattern won't match and the rule is skipped.

    Required rule attributes: same as :func:`compute_msftm_density`.
    Output: DataArray (time, rho, basin, lat) in kg s-1.
    """
    if not isinstance(data, xr.Dataset) or "std_dens_DIVbolus" not in data.data_vars:
        raise ValueError(
            "compute_msftmmpa_density expects 'std_dens_DIVbolus' in input data; got "
            f"{list(data.data_vars) if isinstance(data, xr.Dataset) else type(data)}"
        )
    div = _normalize_dmoc_dim(data["std_dens_DIVbolus"])

    mesh_path = rule.get("mesh_path")
    basin_mask_file = rule.get("basin_mask_file")
    if not all([mesh_path, basin_mask_file]):
        raise ValueError("compute_msftmmpa_density requires 'mesh_path' and 'basin_mask_file' on the rule")

    grid_file = mesh_path if _os.path.isfile(mesh_path) else _os.path.join(mesh_path, "mesh.nc")
    with xr.open_dataset(grid_file) as m:
        lat_nodes = m["lat"].values
    with xr.open_dataset(basin_mask_file) as bm:
        basin_nodes = bm["basin"].values

    psi, lat_centers = _msftm_density_streamfunction(div, lat_nodes, basin_nodes)
    psi_kg = psi * _RHO0

    rho_coord = _resolve_rho_axis(div, rule.get("std_dens"))
    time_coord = div["time"].values if "time" in div.coords else np.arange(psi_kg.shape[0])

    da_out = xr.DataArray(
        psi_kg,
        dims=("time", "rho", "basin", "lat"),
        coords={
            "time": time_coord,
            "rho": rho_coord,
            "basin": list(_CMIP_BASIN_NAMES),
            "lat": lat_centers,
        },
        name=rule.model_variable,
        attrs={
            "units": "kg s-1",
            "long_name": "Ocean Meridional Overturning Mass Streamfunction Due to Parameterized Mesoscale Advection",
        },
    )
    return da_out.to_dataset()


def rechunk_time(data, rule):
    """Rechunk the dask array along the time dim to a larger block.

    Used for write-perf benches: fewer, larger netCDF chunks reduce
    per-chunk HDF5 metadata overhead during save_dataset. Controlled
    by the ``time_chunk_size`` rule attribute (integer number of time
    steps per chunk). No-op if unset or if the data has no time dim.
    """
    n = rule.get("time_chunk_size") if hasattr(rule, "get") else None
    if not n:
        return data
    n = int(n)
    time_dim = None
    for candidate in ("time", "time_counter"):
        if hasattr(data, "dims") and candidate in data.dims:
            time_dim = candidate
            break
    if time_dim is None:
        return data
    return data.chunk({time_dim: n})


# ===========================================================================
# added by LASZLO - 29.04.2026
# LPJ-GUESS depth-layered and pool loaders (mrsll, mrsol, tsl, cSoilPools)
# ===========================================================================

# LPJ-GUESS soil depth layer boundaries (in metres)
# Columns: Depth0.1, Depth0.2, ..., Depth1.5
# These represent the bottom of each 10 cm layer
_DEPTH_LAYER_BOTTOMS = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5])
_DEPTH_LAYER_TOPS = np.concatenate(([0.0], _DEPTH_LAYER_BOTTOMS[:-1]))
_DEPTH_LAYER_CENTRES = (_DEPTH_LAYER_TOPS + _DEPTH_LAYER_BOTTOMS) / 2.0

# Column names as they appear in the .out file header
_DEPTH_COLS = [
    "Depth0.1",
    "Depth0.2",
    "Depth0.3",
    "Depth0.4",
    "Depth0.5",
    "Depth0.6",
    "Depth0.7",
    "Depth0.8",
    "Depth0.9",
    "Depth1",
    "Depth1.1",
    "Depth1.2",
    "Depth1.3",
    "Depth1.4",
    "Depth1.5",
]

# cSoilPools pool names
_POOL_NAMES = ["Fast", "Medium", "Slow"]


def load_lpjguess_monthly_depth(data, rule):
    """
    Load LPJ-GUESS monthly depth-layered .out files.

    Format: Lon / Lat / Year / Mth / Depth0.1 / ... / Depth1.5
    Returns xr.Dataset with dims (time, sdepth, ncells).
    """
    import cftime
    import pandas as pd

    input_collection = rule.inputs[0]
    base_path = input_collection.path
    pattern_str = input_collection.pattern_str

    files = sorted(base_path.glob(pattern_str))
    if not files:
        raise FileNotFoundError(f"No LPJ-GUESS depth files found matching {base_path}/{pattern_str}")
    logger.info(f"Loading {len(files)} LPJ-GUESS monthly depth .out files")

    frames = []
    for f in files:
        logger.info(f"  * {f}")
        df = pd.read_csv(f, sep=r"\s+")
        frames.append(df)
    df_all = pd.concat(frames, ignore_index=True)

    # Year filter: pycmor's --year-start/--year-end CLI flags propagate
    # to rule.year_start / rule.year_end via core/overrides.py. LPJ-GUESS
    # .out files hold every year inline, so filtering at the dataframe
    # level here is the only way to keep cmorized output from leaking
    # non-requested years (cli57 emitted 152 monthly files per year of
    # source data). No-op when neither bound is set.
    _ys = getattr(rule, "year_start", None)
    _ye = getattr(rule, "year_end", None)
    if _ys is not None or _ye is not None:
        _lo = _ys if _ys is not None else int(df_all["Year"].min())
        _hi = _ye if _ye is not None else int(df_all["Year"].max())
        df_all = df_all[(df_all["Year"] >= _lo) & (df_all["Year"] <= _hi)].reset_index(drop=True)
        if df_all.empty:
            raise ValueError(f"LPJ-GUESS loader: no rows in [{_lo}, {_hi}] for rule {getattr(rule, 'name', '?')}")


    years = np.sort(df_all["Year"].unique())

    # Build cell index
    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True]).reset_index(drop=True)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values
    ncells = len(coords_df)

    # Time axis
    times = []
    for yr in years:
        for m in range(1, 13):
            times.append(cftime.DatetimeProlepticGregorian(int(yr), m, 15))

    n_times = len(times)
    n_depths = len(_DEPTH_COLS)
    values = np.full((n_times, n_depths, ncells), np.nan, dtype=np.float64)

    # Vectorized cell + (year, month, depth) indexing
    # (cf. load_lpjguess_monthly for rationale — iterrows held the GIL
    # long enough to break the dask LocalCluster heartbeat).
    coords_df_with_idx = coords_df.copy()
    coords_df_with_idx["_cell_idx"] = np.arange(len(coords_df_with_idx))
    df_merged = df_all.merge(
        coords_df_with_idx[["Lon", "Lat", "_cell_idx"]], on=["Lon", "Lat"], how="left"
    )
    cell_idx_arr = df_merged["_cell_idx"].values
    valid = ~np.isnan(cell_idx_arr)
    cell_idx_int = cell_idx_arr[valid].astype(np.int64)
    yr_idx_arr = np.searchsorted(years, df_merged["Year"].values[valid])
    m_idx_arr = df_merged["Mth"].values[valid].astype(np.int64) - 1
    t_idx_arr = yr_idx_arr * 12 + m_idx_arr
    for d_idx, dcol in enumerate(_DEPTH_COLS):
        values[t_idx_arr, d_idx, cell_idx_int] = df_merged[dcol].values[valid]

    model_variable = rule.get("model_variable", "Total")

    # sdepth coordinate = layer centre depths (metres)
    # sdepth_bnds = layer top/bottom boundaries
    sdepth_bnds = np.column_stack([_DEPTH_LAYER_TOPS, _DEPTH_LAYER_BOTTOMS])

    da = xr.DataArray(
        values,
        dims=["time", "sdepth", "ncells"],
        coords={
            "time": times,
            "sdepth": _DEPTH_LAYER_CENTRES,
            "lon": ("ncells", lon_vals),
            "lat": ("ncells", lat_vals),
        },
        name=model_variable,
    )
    ds = da.to_dataset()

    # Add depth bounds
    ds["sdepth_bnds"] = xr.DataArray(
        sdepth_bnds,
        dims=["sdepth", "bnds"],
        attrs={"long_name": "depth layer boundaries", "units": "m"},
    )
    ds["sdepth"].attrs = {
        "axis": "Z",
        "positive": "down",
        "long_name": "depth",
        "units": "m",
        "bounds": "sdepth_bnds",
    }

    source_units = rule.get("source_units")
    if source_units:
        ds[model_variable].attrs["units"] = source_units

    return ds


def load_lpjguess_monthly_pool(data, rule):
    """
    Load LPJ-GUESS monthly pool .out files (e.g. cSoilPools).

    Format: Lon / Lat / Year / Mth / Fast / Medium / Slow
    Returns xr.Dataset with dims (time, soilCpool, ncells).
    The soilCpool dimension has 3 values: Fast, Medium, Slow.
    """
    import cftime
    import pandas as pd

    input_collection = rule.inputs[0]
    base_path = input_collection.path
    pattern_str = input_collection.pattern_str

    files = sorted(base_path.glob(pattern_str))
    if not files:
        raise FileNotFoundError(f"No LPJ-GUESS pool files found matching {base_path}/{pattern_str}")
    logger.info(f"Loading {len(files)} LPJ-GUESS monthly pool .out files")

    frames = []
    for f in files:
        logger.info(f"  * {f}")
        df = pd.read_csv(f, sep=r"\s+")
        frames.append(df)
    df_all = pd.concat(frames, ignore_index=True)

    # Year filter: pycmor's --year-start/--year-end CLI flags propagate
    # to rule.year_start / rule.year_end via core/overrides.py. LPJ-GUESS
    # .out files hold every year inline, so filtering at the dataframe
    # level here is the only way to keep cmorized output from leaking
    # non-requested years (cli57 emitted 152 monthly files per year of
    # source data). No-op when neither bound is set.
    _ys = getattr(rule, "year_start", None)
    _ye = getattr(rule, "year_end", None)
    if _ys is not None or _ye is not None:
        _lo = _ys if _ys is not None else int(df_all["Year"].min())
        _hi = _ye if _ye is not None else int(df_all["Year"].max())
        df_all = df_all[(df_all["Year"] >= _lo) & (df_all["Year"] <= _hi)].reset_index(drop=True)
        if df_all.empty:
            raise ValueError(f"LPJ-GUESS loader: no rows in [{_lo}, {_hi}] for rule {getattr(rule, 'name', '?')}")


    years = np.sort(df_all["Year"].unique())

    coords_df = df_all[["Lon", "Lat"]].drop_duplicates()
    coords_df = coords_df.sort_values(["Lat", "Lon"], ascending=[False, True]).reset_index(drop=True)
    lon_vals = coords_df["Lon"].values
    lat_vals = coords_df["Lat"].values
    ncells = len(coords_df)

    times = []
    for yr in years:
        for m in range(1, 13):
            times.append(cftime.DatetimeProlepticGregorian(int(yr), m, 15))

    n_times = len(times)
    n_pools = len(_POOL_NAMES)
    values = np.full((n_times, n_pools, ncells), np.nan, dtype=np.float64)

    # Vectorized cell + (year, month, pool) indexing
    # (cf. load_lpjguess_monthly for rationale).
    coords_df_with_idx = coords_df.copy()
    coords_df_with_idx["_cell_idx"] = np.arange(len(coords_df_with_idx))
    df_merged = df_all.merge(
        coords_df_with_idx[["Lon", "Lat", "_cell_idx"]], on=["Lon", "Lat"], how="left"
    )
    cell_idx_arr = df_merged["_cell_idx"].values
    valid = ~np.isnan(cell_idx_arr)
    cell_idx_int = cell_idx_arr[valid].astype(np.int64)
    yr_idx_arr = np.searchsorted(years, df_merged["Year"].values[valid])
    m_idx_arr = df_merged["Mth"].values[valid].astype(np.int64) - 1
    t_idx_arr = yr_idx_arr * 12 + m_idx_arr
    for p_idx, pool in enumerate(_POOL_NAMES):
        values[t_idx_arr, p_idx, cell_idx_int] = df_merged[pool].values[valid]

    model_variable = rule.get("model_variable", "Total")

    da = xr.DataArray(
        values,
        dims=["time", "soilCpool", "ncells"],
        coords={
            "time": times,
            "soilCpool": _POOL_NAMES,
            "lon": ("ncells", lon_vals),
            "lat": ("ncells", lat_vals),
        },
        name=model_variable,
    )
    ds = da.to_dataset()

    ds["soilCpool"].attrs = {
        "long_name": "soil carbon pool",
        "units": "1",
    }

    source_units = rule.get("source_units")
    if source_units:
        ds[model_variable].attrs["units"] = source_units

    return ds


def clip_negative_to_zero(data, rule):
    """Clip values < 0 to 0 (used for melt-only diagnostics).

    Combined with a sign-flipping `scale_factor`, this turns FESOM's net
    snow thickness change `thdgrsnw` (>0 accumulation, <0 melt) into the
    CMIP `snm` snow-melt rate convention (>0 = melting, 0 elsewhere).

    Has no rule attributes.
    """
    import xarray as xr  # noqa: WPS433

    if isinstance(data, xr.Dataset):
        out = data.copy()
        for v in out.data_vars:
            if out[v].dtype.kind in ("f", "i"):
                attrs = out[v].attrs
                out[v] = out[v].where(out[v] >= 0, 0)
                out[v].attrs = attrs
        return out
    attrs = data.attrs.copy()
    out = data.where(data >= 0, 0)
    out.attrs = attrs
    return out


def nan_to_zero(data, rule):
    """Replace NaN / fill-value sentinels with 0, leave finite values alone.

    Used for variables like `vsfcorr` (Virtual Salt Flux Correction) which
    CMIP7 documents as "set to zero in models which receive a real water
    flux" — AWI-CM is such a model, and FESOM emits all-fill output
    instead of zeros. Wherever the source is finite (e.g. if SSS restoring
    is later turned on), real values are preserved.

    Has no rule attributes.
    """
    import xarray as xr  # noqa: WPS433

    if isinstance(data, xr.Dataset):
        out = data.copy()
        for v in out.data_vars:
            if out[v].dtype.kind == "f":
                attrs = out[v].attrs
                out[v] = out[v].fillna(0)
                out[v].attrs = attrs
        return out
    attrs = data.attrs.copy()
    out = data.fillna(0)
    out.attrs = attrs
    return out
