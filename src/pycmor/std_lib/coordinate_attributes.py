"""
Pipeline step to set CF-compliant metadata attributes on coordinate variables.

This module handles setting standard_name, axis, units, and other CF attributes
for coordinate variables (latitude, longitude, vertical coordinates, etc.) to
ensure proper interpretation by xarray and other CF-aware tools.

The time coordinate is handled separately in files.py during the save operation.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Union

import xarray as xr
import yaml

from ..core.logging import logger
from ..core.rule import Rule

SKIPPABLE_TIME_COORD_NAMES = [
    "time",
    "time1",
    "time2",
    "time3",
    "time4",
    "time-intv",
    "time-point",
    "time-fxc",
    "climatology",
    "diurnal-cycle",
]


def _load_coordinate_metadata() -> Dict[str, Dict[str, str]]:
    """
    Load coordinate metadata from YAML file.

    Returns
    -------
    dict
        Dictionary mapping coordinate names to their CF metadata attributes.

    Notes
    -----
    The metadata is loaded from src/pycmor/data/coordinate_metadata.yaml.
    This allows users to add or modify coordinate definitions without
    changing Python code.
    """
    metadata_file = Path(__file__).parent.parent / "data" / "coordinate_metadata.yaml"

    if not metadata_file.exists():
        logger.warning(f"Coordinate metadata file not found: {metadata_file}. " "Using empty metadata dictionary.")
        return {}

    try:
        with open(metadata_file, "r") as f:
            metadata = yaml.safe_load(f)
        logger.debug(f"Loaded coordinate metadata for {len(metadata)} coordinates")
        return metadata
    except Exception as e:
        logger.error(
            f"Failed to load coordinate metadata from {metadata_file}: {e}. " "Using empty metadata dictionary."
        )
        return {}


# Load coordinate metadata from YAML file
# This is loaded once at module import time for performance
COORDINATE_METADATA = _load_coordinate_metadata()


def _get_coordinate_metadata(coord_name: str) -> Optional[Dict[str, str]]:
    """
    Get CF metadata for a coordinate variable.

    Parameters
    ----------
    coord_name : str
        Name of the coordinate variable

    Returns
    -------
    dict or None
        Dictionary of CF attributes, or None if not recognized
    """
    # Direct lookup
    if coord_name in COORDINATE_METADATA:
        return COORDINATE_METADATA[coord_name].copy()

    # Try lowercase match
    coord_lower = coord_name.lower()
    if coord_lower in COORDINATE_METADATA:
        return COORDINATE_METADATA[coord_lower].copy()

    return None


def _load_axis_entries() -> Dict[str, Dict[str, str]]:
    """Load ``axis_entry`` from the vendored CMIP7 coordinate table."""
    path = Path(__file__).parent.parent / "data" / "cmip7" / "CMIP7_coordinate.json"
    try:
        with open(path, "r") as f:
            return json.load(f).get("axis_entry", {}) or {}
    except Exception as exc:
        logger.warning(f"could not load CMIP7_coordinate.json: {exc}; no scalar coordinates will be added")
        return {}


AXIS_ENTRIES = _load_axis_entries()


def add_scalar_coordinates(ds: xr.Dataset, rule: Rule) -> xr.Dataset:
    """Attach the scalar coordinates the data request asks for.

    CMIP7 variables carry their scalar coordinate in the DReq ``dimensions``
    tuple: ``tas`` is ``(longitude, latitude, time, height2m)`` and
    ``sfcWind`` is ``(..., height10m)``. Those entries are not real
    dimensions of the array, they are single-valued coordinates that the
    file has to declare and reference from the data variable's
    ``coordinates`` attribute, e.g.::

        double height ;
            height:units = "m" ;
            height:axis = "Z" ;
            height:positive = "up" ;
            height:standard_name = "height" ;
        float sfcWind(time, cell) ;
            sfcWind:coordinates = "height lat lon" ;

    pycmor emitted neither, so a 10 m wind and a 2 m temperature were
    indistinguishable on disk. The QC does not catch this yet (there are
    no coordinate checks beyond time/lat/lon/lev), but it is required by
    the spec and was raised in the DKRZ review of the cli108 output.

    Values come from the vendored ``CMIP7_coordinate.json``: an entry with
    a non-empty ``value`` is scalar. Entries without one (``sdepth`` and
    other real vertical axes) are left alone, they are dimensions rather
    than scalars and are handled elsewhere.
    """
    drv = getattr(rule, "data_request_variable", None)
    dims = tuple(getattr(drv, "dimensions", ()) or ()) if drv else ()
    if not dims:
        return ds

    for dim in dims:
        entry = AXIS_ENTRIES.get(dim)
        if not entry:
            continue
        raw_value = str(entry.get("value", "") or "").strip()
        if not raw_value:
            # Not a scalar coordinate (e.g. sdepth); leave to the vertical path.
            continue
        out_name = entry.get("out_name") or dim
        if out_name in ds.variables or out_name in ds.coords:
            continue
        try:
            value = float(raw_value)
        except ValueError:
            logger.warning(f"  scalar coordinate {dim!r} has non-numeric value {raw_value!r}; skipping")
            continue

        attrs = {}
        for key in ("standard_name", "long_name", "units", "axis", "positive"):
            val = entry.get(key)
            if val:
                attrs[key] = val
        ds = ds.assign_coords({out_name: xr.DataArray(value, attrs=attrs)})
        ds[out_name].encoding["dtype"] = "float64"
        ds[out_name].encoding["_FillValue"] = None
        logger.info(f"  added scalar coordinate {out_name!r} = {value} {attrs.get('units', '')} (from {dim!r})")

    return ds


def _should_skip_coordinate(coord_name: str, rule: Rule) -> bool:
    """
    Check if a coordinate should be skipped from metadata setting.

    Parameters
    ----------
    coord_name : str
        Name of the coordinate
    rule : Rule
        Processing rule

    Returns
    -------
    bool
        True if coordinate should be skipped
    """
    if coord_name in SKIPPABLE_TIME_COORD_NAMES:
        return True

    if coord_name.endswith("_bnds") or coord_name.endswith("_bounds"):
        return True

    return False


def set_coordinate_attributes(ds: Union[xr.Dataset, xr.DataArray], rule: Rule) -> Union[xr.Dataset, xr.DataArray]:
    """
    Set CF-compliant metadata attributes on coordinate variables.

    This function sets standard_name, axis, units, and positive attributes
    on coordinate variables to ensure proper interpretation by xarray and
    other CF-aware tools.

    Time coordinates are handled separately in files.py during save operation.

    Parameters
    ----------
    ds : xr.Dataset or xr.DataArray
        The dataset or data array to process
    rule : Rule
        Processing rule containing configuration

    Returns
    -------
    xr.Dataset or xr.DataArray
        Dataset/DataArray with coordinate attributes set

    Notes
    -----
    This function:
    - Sets CF standard_name, axis, units for recognized coordinates
    - Sets positive attribute for vertical coordinates
    - Skips time coordinates (handled in files.py)
    - Skips bounds variables
    - Validates existing metadata and handles conflicts based on configuration
    - Logs all attribute changes

    Configuration Options
    ---------------------
    xarray_set_coordinate_attributes : bool
        Enable/disable coordinate attribute setting (default: True)
    xarray_set_coordinates_attribute : bool
        Enable/disable 'coordinates' attribute on data variables (default: True)
    xarray_validate_coordinate_attributes : str
        How to handle conflicting metadata in source data:
        - 'ignore': Silent, keep existing values
        - 'warn': Log warning, keep existing values (default)
        - 'error': Raise ValueError
        - 'fix': Overwrite with correct values

    Examples
    --------
    .. note::
       These examples are illustrative and not verified by doctests.

    .. code-block:: python

        ds = xr.Dataset({
            'tas': (['time', 'lat', 'lon'], data),
        }, coords={
            'lat': np.arange(-90, 90, 1),
            'lon': np.arange(0, 360, 1),
        })
        ds = set_coordinate_attributes(ds, rule)
        print(ds['lat'].attrs)
        # {'standard_name': 'latitude', 'units': 'degrees_north', 'axis': 'Y'}
    """
    # Convert DataArray to Dataset for uniform processing
    original_array = ds.copy()  # This makes a memory copy, so any modifications on ds are not going to be reflected
    arr_name = getattr(ds, "name", "data")
    input_was_dataarray = isinstance(ds, xr.DataArray)
    if input_was_dataarray:
        ds = ds.to_dataset(name=arr_name)

    # Check if coordinate attribute setting is enabled
    if not rule._pycmor_cfg("xarray_set_coordinate_attributes"):
        logger.info("Coordinate attribute setting is disabled in configuration")
        return original_array if input_was_dataarray else ds

    logger.info("[Coordinate Attributes] Setting CF-compliant metadata")

    # Attach DReq-mandated scalar coordinates (height2m/height10m/...)
    # before the attribute pass so they pick up metadata like any other.
    ds = add_scalar_coordinates(ds, rule)

    coords_processed = 0
    coords_skipped = 0

    # Process each coordinate
    for coord_name in ds.coords:
        # Skip coordinates that should not be processed
        if _should_skip_coordinate(coord_name, rule):
            logger.debug(f"  → Skipping '{coord_name}' (handled elsewhere or bounds variable)")
            coords_skipped += 1
            continue

        # Get metadata for this coordinate
        metadata = _get_coordinate_metadata(coord_name)

        if metadata is None:
            logger.debug(f"  → No metadata defined for '{coord_name}'")
            coords_skipped += 1
            continue

        # Set attributes with validation
        logger.info(f"  → Setting attributes for '{coord_name}':")
        validation_mode = rule._pycmor_cfg("xarray_validate_coordinate_attributes")

        for attr_name, attr_value in metadata.items():
            if attr_name not in ds[coord_name].attrs:
                # Attribute not present, set it
                ds[coord_name].attrs[attr_name] = attr_value
                logger.info(f"      • {attr_name} = {attr_value}")
            else:
                # Attribute already exists, validate it
                existing_value = ds[coord_name].attrs[attr_name]

                if existing_value == attr_value:
                    # Values match, all good
                    logger.debug(f"      • {attr_name} already correct ({attr_value})")
                else:
                    # Values don't match, handle according to validation mode
                    if validation_mode == "ignore":
                        logger.debug(
                            f"      • {attr_name} mismatch: got '{existing_value}', "
                            f"expected '{attr_value}' (ignoring)"
                        )
                    elif validation_mode == "warn":
                        logger.warning(
                            f"Coordinate '{coord_name}' has {attr_name}='{existing_value}' "
                            f"but expected '{attr_value}' (keeping existing value)"
                        )
                    elif validation_mode == "error":
                        raise ValueError(
                            f"Invalid {attr_name} for coordinate '{coord_name}': "
                            f"got '{existing_value}', expected '{attr_value}'"
                        )
                    elif validation_mode == "fix":
                        logger.info(f"      • {attr_name} corrected: '{existing_value}' → '{attr_value}'")
                        ds[coord_name].attrs[attr_name] = attr_value
                    else:
                        logger.warning(f"Unknown validation mode '{validation_mode}', defaulting to 'warn'")
                        logger.warning(
                            f"Coordinate '{coord_name}' has {attr_name}='{existing_value}' "
                            f"but expected '{attr_value}'"
                        )

        coords_processed += 1

    logger.info(f"  → Processed {coords_processed} coordinates, skipped {coords_skipped}")

    # Set 'coordinates' attribute on data variables
    if rule._pycmor_cfg("xarray_set_coordinates_attribute"):
        _set_coordinates_attribute(ds, rule)

    # Return in original format
    if input_was_dataarray:
        # [FIXME] PG: This just circumvents the entire function??? I do not understand the idea here?
        # return original_array
        return ds[arr_name]
    return ds


def _set_coordinates_attribute(ds: xr.Dataset, rule: Rule) -> None:
    """
    Set the 'coordinates' attribute on data variables.

    This attribute lists all coordinate variables associated with the data
    variable, which is required for CF compliance especially for auxiliary
    coordinates.

    Parameters
    ----------
    ds : xr.Dataset
        Dataset to process (modified in place)
    rule : Rule
        Processing rule
    """
    logger.info("[Coordinate Attributes] Setting 'coordinates' attribute on data variables")

    for var_name in ds.data_vars:
        # Only list AUXILIARY coordinates (non-dim coords). CF explicitly
        # says the ``coordinates`` attribute is for auxiliary coordinate
        # variables; dim coords are implicit and listing them is legal
        # but redundant per the CMIP/DKRZ style guide (Martin Schupfner
        # review, 2026-06-30).
        var_dims = set(ds[var_name].dims)
        var_coords = [
            coord_name
            for coord_name in ds[var_name].coords
            if coord_name not in var_dims
        ]

        if var_coords:
            # Create coordinates attribute string
            coords_str = " ".join(var_coords)
            # Remove from encoding to avoid conflict with attrs
            ds[var_name].encoding.pop("coordinates", None)
            ds[var_name].attrs["coordinates"] = coords_str
            logger.info(f"  → {var_name}: coordinates = '{coords_str}'")
        else:
            # No auxiliary coords: drop any inherited ``coordinates`` attr
            # from source rather than emit an incorrect list.
            ds[var_name].attrs.pop("coordinates", None)
            ds[var_name].encoding.pop("coordinates", None)


# Alias for consistency with other modules
set_coordinate_attrs = set_coordinate_attributes
