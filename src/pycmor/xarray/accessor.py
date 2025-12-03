"""
xarray Accessors for pycmor

This module provides xarray accessors for interactive coordinate and dimension operations.
The accessors work with both CMIP6 and CMIP7 data request formats and can operate
standalone without full pipeline configuration.

Usage
-----

.. note::
   These examples are illustrative and not verified by doctests.

.. code-block:: python

   import xarray as xr
   ds = xr.open_dataset("model_output.nc")

   # Detect dimension types
   ds.pycmor.dims.detect_types()

   # Map dimensions to CMIP standards
   ds_mapped = ds.pycmor.dims.map_to_cmip(table="Amon", variable="tas")

   # Set coordinate attributes
   ds_mapped = ds_mapped.pycmor.coords.set_attributes()
"""

from typing import Any, Dict, List, Optional

import xarray as xr
from xarray.core.extensions import register_dataarray_accessor, register_dataset_accessor

from ..core.logging import logger
from ..data_request import CMIP6DataRequest, DataRequestVariable

# Check if CMIP7 interface is available
try:
    from ..data_request import CMIP7_API_AVAILABLE, CMIP7Interface
except ImportError:
    CMIP7_API_AVAILABLE = False
    CMIP7Interface = None


def _build_config_dict(**kwargs):
    """
    Build a configuration dictionary from kwargs.

    Converts user-friendly parameter names to internal config keys.

    Parameters
    ----------
    **kwargs
        User-provided configuration options

    Returns
    -------
    dict
        Configuration dictionary compatible with pycmor config system
    """
    # Map user-friendly names to internal config keys
    config_map = {
        # Coordinate attributes
        "enable": "xarray_set_coordinate_attributes",
        "validate": "xarray_validate_coordinate_attributes",
        "set_coordinates_attr": "xarray_set_coordinates_attribute",
        # Dimension mapping
        "enable_dim_mapping": "xarray_enable_dimension_mapping",
        "dim_validation": "dimension_mapping_validation",
        "allow_override": "dimension_mapping_allow_override",
        "user_mapping": "dimension_mapping",
    }

    config = {}
    for key, value in kwargs.items():
        # Use mapped key if available, otherwise use as-is
        config_key = config_map.get(key, key)
        config[config_key] = value

    return config


def _lookup_data_request_variable(
    data_request_variable: Optional[DataRequestVariable] = None,
    table: Optional[str] = None,
    variable: Optional[str] = None,
    compound_name: Optional[str] = None,
    variable_spec: Optional[str] = None,
    cmor_version: Optional[str] = None,
    **kwargs,
) -> Optional[DataRequestVariable]:
    """
    Flexible lookup for DataRequestVariable supporting CMIP6 and CMIP7.

    Priority order:
    1. data_request_variable (if provided, use directly)
    2. CMIP6: table + variable
    3. CMIP7: compound_name
    4. Smart: variable_spec (auto-detect format)
    5. None (no CMIP table constraints)

    Parameters
    ----------
    data_request_variable : DataRequestVariable, optional
        Pre-constructed DataRequestVariable
    table : str, optional
        CMIP6 table name (e.g., 'Amon', 'Omon')
    variable : str, optional
        CMIP6 variable name (e.g., 'tas', 'pr')
    compound_name : str, optional
        CMIP7 compound name or CMIP6-style name for backward compatibility
    variable_spec : str, optional
        Auto-detect format (CMIP6 'Table.variable' or CMIP7 compound name)
    cmor_version : str, optional
        'CMIP6' or 'CMIP7' (can be auto-detected)
    **kwargs
        Additional parameters (ignored)

    Returns
    -------
    DataRequestVariable or None
        The requested variable specification, or None if not enough info

    Raises
    ------
    ValueError
        If arguments are ambiguous or conflicting
    """
    # Priority 1: Direct DataRequestVariable
    if data_request_variable is not None:
        return data_request_variable

    # Priority 2: CMIP6 table + variable
    if table is not None and variable is not None:
        if compound_name is not None or variable_spec is not None:
            raise ValueError(
                "Cannot specify both CMIP6 (table+variable) and CMIP7 (compound_name) parameters simultaneously"
            )

        logger.debug(f"Looking up CMIP6 variable: {table}.{variable}")
        try:
            dreq = CMIP6DataRequest()
            drv = dreq.get_variable(table=table, variable=variable)
            return drv
        except Exception as e:
            logger.warning(f"Failed to lookup CMIP6 variable {table}.{variable}: {e}")
            return None

    # Priority 3: CMIP7 compound_name
    if compound_name is not None:
        if variable_spec is not None:
            raise ValueError("Cannot specify both compound_name and variable_spec")

        # Detect if this is CMIP6-style (backward compatibility)
        if "." in compound_name and compound_name.count(".") == 1:
            # Could be CMIP6-style "Table.variable"
            parts = compound_name.split(".")
            if len(parts[0]) < 10:  # Table names are short
                logger.debug(f"Compound name '{compound_name}' looks like CMIP6 format")
                table_name, var_name = parts
                return _lookup_data_request_variable(table=table_name, variable=var_name, cmor_version="CMIP6")

        # Try CMIP7 lookup
        if not CMIP7_API_AVAILABLE:
            logger.warning(
                "CMIP7 compound name specified but CMIP7 API not available. "
                "Install with: pip install CMIP7-data-request-api"
            )
            return None

        logger.debug(f"Looking up CMIP7 variable: {compound_name}")
        try:
            interface = CMIP7Interface()
            # TODO: Load appropriate version
            metadata = interface.get_variable_metadata(compound_name)
            if metadata:
                # Convert to DataRequestVariable
                # This would need CMIP7DataRequestVariable.from_metadata() method
                logger.warning("CMIP7 DataRequestVariable conversion not yet implemented")
                return None
            return None
        except Exception as e:
            logger.warning(f"Failed to lookup CMIP7 variable {compound_name}: {e}")
            return None

    # Priority 4: Smart detection from variable_spec
    if variable_spec is not None:
        logger.debug(f"Auto-detecting format for variable_spec: {variable_spec}")

        # CMIP6 format: Table.variable (e.g., "Amon.tas")
        if "." in variable_spec:
            parts = variable_spec.split(".")
            if len(parts) == 2:
                # Likely CMIP6 format
                return _lookup_data_request_variable(table=parts[0], variable=parts[1], cmor_version="CMIP6")
            elif len(parts) == 5:
                # Likely CMIP7 format: realm.variable.branding.frequency.region
                return _lookup_data_request_variable(compound_name=variable_spec, cmor_version="CMIP7")

        logger.warning(f"Could not auto-detect format for variable_spec: {variable_spec}")
        return None

    # Priority 5: No CMIP table specified
    logger.debug("No CMIP variable specification provided, operating in standalone mode")
    return None


class CoordinateAccessor:
    """
    Accessor for coordinate attribute operations.

    Access via: ds.pycmor.coords
    """

    def __init__(self, xarray_obj):
        """
        Initialize coordinate accessor.

        Parameters
        ----------
        xarray_obj : Dataset or DataArray
            The xarray object to operate on
        """
        self._obj = xarray_obj

    def set_attributes(
        self,
        rule=None,
        enable: bool = True,
        validate: str = "warn",
        set_coordinates_attr: bool = True,
        **kwargs,
    ):
        """
        Set CF-compliant attributes on coordinate variables.

        Parameters
        ----------
        rule : Rule, optional
            Rule object with configuration. If provided, other kwargs ignored.
        enable : bool
            Enable coordinate attribute setting (default: True)
        validate : str
            Validation mode: 'ignore', 'warn', 'error', 'fix' (default: 'warn')
        set_coordinates_attr : bool
            Set 'coordinates' attribute on data variables (default: True)
        **kwargs
            Additional configuration options

        Returns
        -------
        Dataset or DataArray
            Data with coordinate attributes set

        Examples
        --------
        .. code-block:: python

            ds_with_attrs = ds.pycmor.coords.set_attributes()
            ds_with_attrs = ds.pycmor.coords.set_attributes(validate='fix')
        """
        # Import here to avoid circular dependency
        from ..std_lib.coordinate_attributes import set_coordinate_attributes

        if rule is not None:
            # Use rule directly
            return set_coordinate_attributes(self._obj, rule)

        # Build mock rule from kwargs
        from types import SimpleNamespace

        config = _build_config_dict(
            enable=enable,
            validate=validate,
            set_coordinates_attr=set_coordinates_attr,
            **kwargs,
        )

        # Create minimal rule-like object
        mock_rule = SimpleNamespace()
        mock_rule._pycmor_cfg = lambda key, default=None: config.get(key, default)

        return set_coordinate_attributes(self._obj, mock_rule)

    def get_metadata(self, coord_name: str) -> Optional[Dict[str, str]]:
        """
        Get CF metadata for a coordinate.

        Parameters
        ----------
        coord_name : str
            Name of coordinate

        Returns
        -------
        dict or None
            Metadata dictionary or None if not recognized

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            lat_meta = ds.pycmor.coords.get_metadata('lat')
            print(lat_meta)
            # {'standard_name': 'latitude', 'units': 'degrees_north', 'axis': 'Y'}
        """
        from ..std_lib.coordinate_attributes import _get_coordinate_metadata

        return _get_coordinate_metadata(coord_name)

    def list_recognized(self) -> List[str]:
        """
        List all recognized coordinate names.

        Returns
        -------
        list
            All coordinate names in metadata YAML

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            coords = ds.pycmor.coords.list_recognized()
            print(coords[:5])
            # ['lat', 'latitude', 'lon', 'longitude', 'plev19']
        """
        from ..std_lib.coordinate_attributes import COORDINATE_METADATA

        return list(COORDINATE_METADATA.keys())

    def validate(self, mode: str = "warn") -> Dict[str, Any]:
        """
        Validate existing coordinate attributes.

        Parameters
        ----------
        mode : str
            How to handle issues: 'ignore', 'warn', 'error' (default: 'warn')

        Returns
        -------
        dict
            Validation results by coordinate

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            results = ds.pycmor.coords.validate()
            print(results)
            # {'lat': {'valid': True}, 'lon': {'valid': True, 'warnings': [...]}}
        """
        from ..std_lib.coordinate_attributes import _get_coordinate_metadata

        results = {}

        # Get all coordinates in the dataset
        coords = list(self._obj.coords)

        for coord_name in coords:
            coord = self._obj.coords[coord_name]
            expected_meta = _get_coordinate_metadata(coord_name)

            if expected_meta is None:
                results[coord_name] = {"valid": None, "message": "Coordinate not recognized"}
                continue

            # Check each expected attribute
            issues = []
            for attr_name, expected_value in expected_meta.items():
                actual_value = coord.attrs.get(attr_name)
                if actual_value != expected_value:
                    issues.append(
                        {
                            "attribute": attr_name,
                            "expected": expected_value,
                            "actual": actual_value,
                        }
                    )

            if issues:
                results[coord_name] = {"valid": False, "issues": issues}
                if mode == "warn":
                    logger.warning(f"Coordinate '{coord_name}' has {len(issues)} attribute issue(s)")
                elif mode == "error":
                    raise ValueError(f"Coordinate '{coord_name}' has invalid attributes: {issues}")
            else:
                results[coord_name] = {"valid": True}

        return results


class DimensionAccessor:
    """
    Accessor for dimension mapping operations.

    Access via: ds.pycmor.dims
    """

    def __init__(self, xarray_obj):
        """
        Initialize dimension accessor.

        Parameters
        ----------
        xarray_obj : Dataset or DataArray
            The xarray object to operate on
        """
        self._obj = xarray_obj

    def detect_types(self) -> Dict[str, Optional[str]]:
        """
        Detect dimension types in dataset.

        Returns
        -------
        dict
            Mapping of {dim_name: dim_type}

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            types = ds.pycmor.dims.detect_types()
            print(types)
            # {'time': 'time', 'lev': 'pressure', 'latitude': 'latitude', 'longitude': 'longitude'}
        """
        from ..std_lib.dimension_mapping import DimensionMapper

        mapper = DimensionMapper()

        # Convert to Dataset if DataArray
        if isinstance(self._obj, xr.DataArray):
            ds = self._obj.to_dataset()
        else:
            ds = self._obj

        dim_types = {}
        for dim_name in ds.sizes.keys():
            dim_type = mapper.detect_dimension_type(ds, dim_name)
            dim_types[dim_name] = dim_type

        return dim_types

    def map_to_cmip(
        self,
        rule=None,
        data_request_variable: Optional[DataRequestVariable] = None,
        # CMIP6 style
        table: Optional[str] = None,
        variable: Optional[str] = None,
        # CMIP7 style
        compound_name: Optional[str] = None,
        # Smart/manual
        variable_spec: Optional[str] = None,
        target_dimensions: Optional[List[str]] = None,
        # Config
        cmor_version: Optional[str] = None,
        user_mapping: Optional[Dict[str, str]] = None,
        enable: bool = True,
        validate: str = "warn",
        allow_override: bool = True,
        **kwargs,
    ):
        """
        Map dimensions to CMIP standards.

        Multiple ways to specify target variable:
        1. Pass Rule object (pipeline integration)
        2. Pass DataRequestVariable directly
        3. CMIP6: table + variable
        4. CMIP7: compound_name
        5. Smart: variable_spec (auto-detect)
        6. Manual: target_dimensions list

        Parameters
        ----------
        rule : Rule, optional
            Rule object with full configuration
        data_request_variable : DataRequestVariable, optional
            CMIP variable specification
        table : str, optional
            CMIP6 table name
        variable : str, optional
            CMIP6 variable name
        compound_name : str, optional
            CMIP7 compound name
        variable_spec : str, optional
            Auto-detect format
        target_dimensions : list, optional
            Manual dimension list
        cmor_version : str, optional
            'CMIP6' or 'CMIP7'
        user_mapping : dict, optional
            User dimension renames
        enable : bool
            Enable dimension mapping
        validate : str
            Validation mode
        allow_override : bool
            Allow overriding CMIP dims
        **kwargs
            Additional config options

        Returns
        -------
        Dataset or DataArray
            Data with dimensions mapped

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            # CMIP6
            ds_mapped = ds.pycmor.dims.map_to_cmip(table="Amon", variable="tas")

            # CMIP7
            ds_mapped = ds.pycmor.dims.map_to_cmip(
                compound_name="atmos.tas.tavg-h2m-hxy-u.mon.GLB"
            )

            # Manual
            ds_mapped = ds.pycmor.dims.map_to_cmip(
                target_dimensions=['time', 'plev19', 'lat', 'lon']
            )
        """
        from ..std_lib.dimension_mapping import map_dimensions

        if rule is not None:
            # Use rule directly
            return map_dimensions(self._obj, rule)

        # Lookup DataRequestVariable if needed
        if data_request_variable is None and target_dimensions is None:
            data_request_variable = _lookup_data_request_variable(
                data_request_variable=data_request_variable,
                table=table,
                variable=variable,
                compound_name=compound_name,
                variable_spec=variable_spec,
                cmor_version=cmor_version,
            )

        # Build mock rule
        from types import SimpleNamespace

        config = _build_config_dict(
            enable_dim_mapping=enable,
            dim_validation=validate,
            allow_override=allow_override,
            user_mapping=user_mapping or {},
            **kwargs,
        )

        # If target_dimensions provided or no DRV, use flexible approach
        if target_dimensions is not None or data_request_variable is None:
            from ..std_lib.dimension_mapping import DimensionMapper

            # Convert to Dataset if DataArray
            was_dataarray = isinstance(self._obj, xr.DataArray)
            if was_dataarray:
                da_name = self._obj.name or "data"
                ds = self._obj.to_dataset(name=da_name)
            else:
                ds = self._obj

            mapper = DimensionMapper()

            # Create and apply mapping
            mapping = mapper.create_mapping_flexible(
                ds=ds,
                data_request_variable=data_request_variable,
                target_dimensions=target_dimensions,
                user_mapping=user_mapping or {},
                allow_override=allow_override,
            )

            ds_mapped = mapper.apply_mapping(ds, mapping)

            if was_dataarray:
                return ds_mapped[da_name]
            return ds_mapped

        # Standard path with Rule and DataRequestVariable
        mock_rule = SimpleNamespace()
        mock_rule._pycmor_cfg = lambda key, default=None: config.get(key, default)
        mock_rule.data_request_variable = data_request_variable

        return map_dimensions(self._obj, mock_rule)

    def create_mapping(self, **kwargs) -> Dict[str, str]:
        """
        Create dimension mapping without applying it.

        Low-level method for expert use. See map_to_cmip for parameters.

        Returns
        -------
        dict
            Dimension mapping {source_name: target_name}

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            mapping = ds.pycmor.dims.create_mapping(table="Amon", variable="tas")
            print(mapping)
            # {'latitude': 'lat', 'longitude': 'lon', 'time': 'time'}
        """
        from ..std_lib.dimension_mapping import DimensionMapper

        # Extract relevant parameters
        data_request_variable = kwargs.get("data_request_variable")
        table = kwargs.get("table")
        variable = kwargs.get("variable")
        compound_name = kwargs.get("compound_name")
        variable_spec = kwargs.get("variable_spec")
        target_dimensions = kwargs.get("target_dimensions")
        cmor_version = kwargs.get("cmor_version")
        user_mapping = kwargs.get("user_mapping")
        allow_override = kwargs.get("allow_override", True)

        # Lookup DataRequestVariable if needed
        if data_request_variable is None and target_dimensions is None:
            data_request_variable = _lookup_data_request_variable(
                data_request_variable=data_request_variable,
                table=table,
                variable=variable,
                compound_name=compound_name,
                variable_spec=variable_spec,
                cmor_version=cmor_version,
            )

        # Convert to Dataset if DataArray
        if isinstance(self._obj, xr.DataArray):
            ds = self._obj.to_dataset()
        else:
            ds = self._obj

        mapper = DimensionMapper()
        mapping = mapper.create_mapping_flexible(
            ds=ds,
            data_request_variable=data_request_variable,
            target_dimensions=target_dimensions,
            user_mapping=user_mapping,
            allow_override=allow_override,
        )

        return mapping

    def apply_mapping(self, mapping: Dict[str, str]):
        """
        Apply a dimension mapping to the dataset.

        Parameters
        ----------
        mapping : dict
            Dimension mapping {source_name: target_name}

        Returns
        -------
        Dataset or DataArray
            Data with renamed dimensions

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            mapping = {'latitude': 'lat', 'longitude': 'lon'}
            ds_mapped = ds.pycmor.dims.apply_mapping(mapping)
        """
        from ..std_lib.dimension_mapping import DimensionMapper

        mapper = DimensionMapper()

        # Convert to Dataset if DataArray
        was_dataarray = isinstance(self._obj, xr.DataArray)
        if was_dataarray:
            da_name = self._obj.name or "data"
            ds = self._obj.to_dataset(name=da_name)
        else:
            ds = self._obj

        ds_mapped = mapper.apply_mapping(ds, mapping)

        if was_dataarray:
            return ds_mapped[da_name]
        return ds_mapped


@register_dataset_accessor("pycmor")
class PycmorAccessor:
    """
    Main pycmor accessor with sub-accessors for different operations.

    Access coordinate operations via: ds.pycmor.coords
    Access dimension operations via: ds.pycmor.dims
    """

    def __init__(self, xarray_obj):
        """
        Initialize pycmor accessor.

        Parameters
        ----------
        xarray_obj : Dataset
            The xarray Dataset to operate on
        """
        self._obj = xarray_obj
        self._coords_accessor = None
        self._dims_accessor = None

    @property
    def coords(self) -> CoordinateAccessor:
        """
        Access coordinate attribute operations.

        Returns
        -------
        CoordinateAccessor
            Accessor for coordinate operations

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            ds.pycmor.coords.set_attributes()
            ds.pycmor.coords.get_metadata('lat')
        """
        if self._coords_accessor is None:
            self._coords_accessor = CoordinateAccessor(self._obj)
        return self._coords_accessor

    @property
    def dims(self) -> DimensionAccessor:
        """
        Access dimension mapping operations.

        Returns
        -------
        DimensionAccessor
            Accessor for dimension operations

        Examples
        --------
        .. note::
           These examples are illustrative and not verified by doctests.

        .. code-block:: python

            ds.pycmor.dims.detect_types()
            ds.pycmor.dims.map_to_cmip(table="Amon", variable="tas")
        """
        if self._dims_accessor is None:
            self._dims_accessor = DimensionAccessor(self._obj)
        return self._dims_accessor


@register_dataarray_accessor("pycmor")
class PycmorDataArrayAccessor(PycmorAccessor):
    """
    Pycmor accessor for DataArrays.

    Same interface as PycmorAccessor, automatically converts to Dataset
    for operations and converts back to DataArray for results.
    """

    pass
