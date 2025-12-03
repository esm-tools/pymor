# xarray Accessor Implementation Plan

## Overview

Add version-agnostic xarray accessors (`.pycmor.coords` and `.pycmor.dims`) that work seamlessly with both CMIP6 table-based naming and CMIP7 compound names. Enable interactive exploration and programmatic use without full pipeline setup.

## Effort Estimate

**Medium (2-3 days)**

## CMIP6 vs CMIP7 Design Considerations

### Current Variable Identification Systems

- **CMIP6**: Table + Variable (e.g., `table="Amon"`, `variable="tas"`)
- **CMIP7**: Compound Name (e.g., `"atmos.tas.tavg-h2m-hxy-u.mon.GLB"`)
  - Also supports CMIP6 backward compatibility: `"Amon.tas"`
- **Both**: Use `DataRequestVariable` with `.dimensions` property

### Version-Agnostic Accessor API Strategy

```python
# Option 1: Pass DataRequestVariable directly (works for both CMIP6/7)
ds.pycmor.dims.map_to_cmip(data_request_variable=drv)

# Option 2: Lookup by CMIP6 table + variable
ds.pycmor.dims.map_to_cmip(table="Amon", variable="tas", cmor_version="CMIP6")

# Option 3: Lookup by CMIP7 compound name
ds.pycmor.dims.map_to_cmip(compound_name="atmos.tas.tavg-h2m-hxy-u.mon.GLB", cmor_version="CMIP7")

# Option 4: Lookup by CMIP7 backward-compatible name
ds.pycmor.dims.map_to_cmip(compound_name="Amon.tas", cmor_version="CMIP7")

# Option 5: Smart inference (tries to determine from arguments)
ds.pycmor.dims.map_to_cmip(variable_spec="Amon.tas")  # Detects CMIP6 format
ds.pycmor.dims.map_to_cmip(variable_spec="atmos.tas.tavg-h2m-hxy-u.mon.GLB")  # Detects CMIP7

# Option 6: Standalone (no CMIP table, just basic types)
ds.pycmor.dims.map_to_cmip(target_dims=['time', 'plev19', 'lat', 'lon'])
```

## Implementation Tasks

### Task 1: Create Core Accessor Module (~5 hours)

**File**: `src/pycmor/core/xarray_accessors.py`

**Deliverables**:
- Base accessor `PycmorAccessor` for Dataset/DataArray
- Sub-accessor infrastructure (coords, dims namespaces)
- Version-agnostic variable lookup helper:
  - Detect CMIP version from arguments
  - Route to appropriate DataRequest (CMIP6DataRequest vs CMIP7DataRequest)
  - Fall back to manual dimension specification
- Configuration builder (kwargs → Rule-like config)
- Register with `@register_dataset_accessor("pycmor")`

### Task 2: Add DataRequestVariable Lookup Helper (~3 hours)

**File**: `src/pycmor/core/xarray_accessors.py` (helper functions)

```python
def _lookup_data_request_variable(
    data_request_variable=None,
    table=None,
    variable=None,
    compound_name=None,
    variable_spec=None,
    cmor_version=None,
    **kwargs
):
    """
    Flexible lookup that handles CMIP6 and CMIP7 variable specifications.

    Priority:
    1. data_request_variable (if provided, use directly)
    2. CMIP6: table + variable
    3. CMIP7: compound_name
    4. Smart: variable_spec (auto-detect format)
    5. None (dimension mapping without CMIP table constraints)
    """
```

### Task 3: Refactor Coordinate Attributes (~3 hours)

**File**: `src/pycmor/std_lib/coordinate_attributes.py`

**Changes**:
- Extract config reading into `_build_config_dict(**kwargs)`
- Add `set_coordinate_attributes_standalone(ds, **kwargs)`
- Keep existing `set_coordinate_attributes(ds, rule)` unchanged

**Note**: Coordinate attributes don't depend on CMIP version - they're purely CF-based.

**Parameters exposed**:
- `enable=True` - Enable/disable coordinate attribute setting
- `validate='warn'` - Validation mode (ignore/warn/error/fix)
- `set_coordinates_attr=True` - Set 'coordinates' attribute on data variables

### Task 4: Refactor Dimension Mapping (~5 hours)

**File**: `src/pycmor/std_lib/dimension_mapping.py`

**Changes**:
- Add `create_mapping_flexible()` method to DimensionMapper:
  ```python
  def create_mapping_flexible(
      self,
      ds,
      data_request_variable=None,  # Optional now
      target_dimensions=None,      # Manual dimension list
      user_mapping=None,
      allow_override=True
  ):
      """
      Create mapping with or without DataRequestVariable.
      If target_dimensions provided, use those as CMIP dims.
      If data_request_variable is None, just do smart type-based mapping.
      """
  ```
- Add `DimensionMapper.detect_all_types(ds)` - return dict of detected types
- Extract CMIP validation into separate method (can be skipped if no DRV)

**Parameters exposed**:
- `data_request_variable=None` - DRV object (CMIP6 or CMIP7)
- `target_dimensions=None` - Manual list like `['time', 'plev19', 'lat', 'lon']`
- `user_mapping={}` - User overrides
- `enable=True`
- `validate='warn'`
- `allow_override=True`

### Task 5: Build Accessor Classes (~6 hours)

**File**: `src/pycmor/core/xarray_accessors.py`

#### PycmorAccessor (`.pycmor`)

```python
@register_dataset_accessor("pycmor")
class PycmorAccessor:
    """Main pycmor accessor with sub-accessors for different operations."""

    def __init__(self, xarray_obj):
        self._obj = xarray_obj
        self._coords_accessor = None
        self._dims_accessor = None

    @property
    def coords(self):
        """Access coordinate attribute operations."""
        if self._coords_accessor is None:
            self._coords_accessor = CoordinateAccessor(self._obj)
        return self._coords_accessor

    @property
    def dims(self):
        """Access dimension mapping operations."""
        if self._dims_accessor is None:
            self._dims_accessor = DimensionAccessor(self._obj)
        return self._dims_accessor
```

#### CoordinateAccessor (`.pycmor.coords`)

```python
class CoordinateAccessor:
    """Accessor for coordinate attribute operations."""

    def __init__(self, xarray_obj):
        self._obj = xarray_obj

    def set_attributes(self, rule=None, enable=True, validate='warn', **kwargs):
        """
        Set CF-compliant attributes on coordinate variables.

        Parameters
        ----------
        rule : Rule, optional
            Rule object with configuration. If provided, other kwargs ignored.
        enable : bool
            Enable coordinate attribute setting
        validate : str
            Validation mode: 'ignore', 'warn', 'error', 'fix'
        **kwargs
            Additional configuration options

        Returns
        -------
        Dataset or DataArray
            Data with coordinate attributes set
        """

    def get_metadata(self, coord_name):
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
        """

    def list_recognized(self):
        """
        List all recognized coordinate names.

        Returns
        -------
        list
            All coordinate names in metadata YAML
        """

    def validate(self, mode='warn'):
        """
        Validate existing coordinate attributes.

        Parameters
        ----------
        mode : str
            How to handle issues: 'ignore', 'warn', 'error'

        Returns
        -------
        dict
            Validation results by coordinate
        """
```

#### DimensionAccessor (`.pycmor.dims`)

```python
class DimensionAccessor:
    """Accessor for dimension mapping operations."""

    def __init__(self, xarray_obj):
        self._obj = xarray_obj

    def detect_types(self):
        """
        Detect dimension types in dataset.

        Returns
        -------
        dict
            Mapping of {dim_name: dim_type}

        Examples
        --------
        >>> ds.pycmor.dims.detect_types()
        {'time': 'time', 'lev': 'pressure', 'latitude': 'latitude', 'longitude': 'longitude'}
        """

    def map_to_cmip(
        self,
        rule=None,
        data_request_variable=None,
        # CMIP6 style:
        table=None,
        variable=None,
        # CMIP7 style:
        compound_name=None,
        # Smart/manual:
        variable_spec=None,
        target_dimensions=None,
        # Config:
        cmor_version=None,
        user_mapping=None,
        **kwargs
    ):
        """
        Map dimensions to CMIP standards.

        Flexible method that supports multiple ways of specifying target variable:

        1. Pass Rule object (pipeline integration)
        2. Pass DataRequestVariable directly
        3. CMIP6: Specify table + variable
        4. CMIP7: Specify compound_name
        5. Smart: Specify variable_spec (auto-detect format)
        6. Manual: Specify target_dimensions list

        Parameters
        ----------
        rule : Rule, optional
            Rule object with full configuration
        data_request_variable : DataRequestVariable, optional
            CMIP variable specification (CMIP6 or CMIP7)
        table : str, optional
            CMIP6 table name (e.g., 'Amon', 'Omon')
        variable : str, optional
            CMIP6 variable name (e.g., 'tas', 'pr')
        compound_name : str, optional
            CMIP7 compound name (e.g., 'atmos.tas.tavg-h2m-hxy-u.mon.GLB')
            or CMIP6-style for backward compatibility (e.g., 'Amon.tas')
        variable_spec : str, optional
            Auto-detect format from string (CMIP6 or CMIP7 style)
        target_dimensions : list, optional
            Manual dimension list (e.g., ['time', 'plev19', 'lat', 'lon'])
        cmor_version : str, optional
            'CMIP6' or 'CMIP7' (can usually be auto-detected)
        user_mapping : dict, optional
            User-specified dimension renames {source: target}
        **kwargs
            Additional config options (enable, validate, allow_override, etc.)

        Returns
        -------
        Dataset or DataArray
            Data with dimensions mapped to CMIP names

        Examples
        --------
        # CMIP6 style
        >>> ds_mapped = ds.pycmor.dims.map_to_cmip(table="Amon", variable="tas")

        # CMIP7 style
        >>> ds_mapped = ds.pycmor.dims.map_to_cmip(
        ...     compound_name="atmos.tas.tavg-h2m-hxy-u.mon.GLB"
        ... )

        # Smart detection
        >>> ds_mapped = ds.pycmor.dims.map_to_cmip(variable_spec="Amon.tas")

        # Manual
        >>> ds_mapped = ds.pycmor.dims.map_to_cmip(
        ...     target_dimensions=['time', 'plev19', 'lat', 'lon']
        ... )
        """

    def create_mapping(self, **kwargs):
        """
        Create dimension mapping without applying it.

        Low-level method for expert use. See map_to_cmip for parameters.

        Returns
        -------
        dict
            Dimension mapping {source_name: target_name}
        """

    def apply_mapping(self, mapping):
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
        """
```

### Task 6: Documentation (~3 hours)

**New file**: `doc/xarray_accessors.rst`

**Sections**:
1. Quick Start
2. CMIP6 Usage Examples
3. CMIP7 Usage Examples
4. Version-Agnostic Patterns
5. Standalone Usage (no CMIP tables)
6. API Reference
7. Comparison with Pipeline Usage

### Task 7: Tests (~5 hours)

**New file**: `tests/unit/test_xarray_accessors.py`

**Test coverage**:
- CMIP6-style variable lookup (table + variable)
- CMIP7-style variable lookup (compound name)
- CMIP7 backward compatibility (CMIP6 format in CMIP7)
- Smart detection (auto-detect format from variable_spec)
- Standalone mode (no CMIP tables)
- Rule passthrough
- Error handling for ambiguous args
- Integration: dims + coords together

### Task 8: Integration Updates (~1 hour)

**Modified files**:
- `src/pycmor/std_lib/__init__.py` - Export new standalone functions
- `src/pycmor/__init__.py` - Import accessors for auto-registration
- `doc/index.rst` - Add link to accessor documentation

## API Usage Examples

### CMIP6 Usage

```python
import xarray as xr

# Load data
ds = xr.open_dataset("model_output.nc")

# Detect dimension types (no CMIP context needed)
dim_types = ds.pycmor.dims.detect_types()
# {'time': 'time', 'lev': 'pressure', 'latitude': 'latitude', 'longitude': 'longitude'}

# Map to CMIP6 standard (Amon table, tas variable)
ds_mapped = ds.pycmor.dims.map_to_cmip(
    table="Amon",
    variable="tas",
    cmor_version="CMIP6"
)
# Dimensions: time, lat, lon (mapped from latitude/longitude)

# Set coordinate attributes
ds_mapped = ds_mapped.pycmor.coords.set_attributes(validate='warn')

# Check what metadata would be set
lat_meta = ds_mapped.pycmor.coords.get_metadata('lat')
# {'standard_name': 'latitude', 'units': 'degrees_north', 'axis': 'Y'}
```

### CMIP7 Usage

```python
import xarray as xr

# Load data
ds = xr.open_dataset("model_output.nc")

# Map to CMIP7 standard using compound name
ds_mapped = ds.pycmor.dims.map_to_cmip(
    compound_name="atmos.tas.tavg-h2m-hxy-u.mon.GLB",
    cmor_version="CMIP7"
)

# Or use CMIP6-style in CMIP7 (backward compatibility)
ds_mapped = ds.pycmor.dims.map_to_cmip(
    compound_name="Amon.tas",
    cmor_version="CMIP7"
)

# Set coordinate attributes (same as CMIP6)
ds_mapped = ds_mapped.pycmor.coords.set_attributes()
```

### Smart Detection

```python
# Auto-detect format from variable_spec
ds_mapped = ds.pycmor.dims.map_to_cmip(
    variable_spec="Amon.tas"  # Detects CMIP6 format
)

ds_mapped = ds.pycmor.dims.map_to_cmip(
    variable_spec="atmos.tas.tavg-h2m-hxy-u.mon.GLB"  # Detects CMIP7 format
)
```

### Standalone (No CMIP Tables)

```python
# Just intelligent dimension detection and renaming
ds_mapped = ds.pycmor.dims.map_to_cmip(
    target_dimensions=['time', 'plev19', 'lat', 'lon'],
    user_mapping={'lev': 'plev19'}  # Manual hint
)

# Explore available coordinate metadata
recognized = ds.pycmor.coords.list_recognized()
# ['lat', 'latitude', 'lon', 'longitude', 'plev19', 'olevel', ...]

# Get metadata for exploration
lat_meta = ds.pycmor.coords.get_metadata('lat')
# {'standard_name': 'latitude', 'units': 'degrees_north', 'axis': 'Y'}
```

### Pipeline Usage (Unchanged)

```python
# Pipeline code continues to work as before
from pycmor.std_lib import map_dimensions, set_coordinate_attributes

def my_pipeline_step(data, rule):
    data = map_dimensions(data, rule)  # Uses rule._pycmor_cfg
    data = set_coordinate_attributes(data, rule)
    return data
```

## File Changes Summary

### New Files (3)

1. `src/pycmor/core/xarray_accessors.py` (~400 lines)
   - PycmorAccessor class
   - CoordinateAccessor class
   - DimensionAccessor class
   - Helper functions for variable lookup
   - Configuration builders

2. `doc/xarray_accessors.rst` (~250 lines)
   - User documentation
   - API reference
   - Usage examples for CMIP6 and CMIP7

3. `tests/unit/test_xarray_accessors.py` (~500 lines)
   - Test suite covering all usage patterns

### Modified Files (6)

1. `src/pycmor/std_lib/coordinate_attributes.py` (+~50 lines)
   - Add `set_coordinate_attributes_standalone()` function
   - Add `_build_config_dict()` helper

2. `src/pycmor/std_lib/dimension_mapping.py` (+~100 lines)
   - Add `DimensionMapper.create_mapping_flexible()` method
   - Add `DimensionMapper.detect_all_types()` method
   - Add `map_dimensions_standalone()` function

3. `src/pycmor/data_request/__init__.py` (+~20 lines)
   - Export helper functions for variable lookup

4. `src/pycmor/std_lib/__init__.py` (+~20 lines)
   - Export new standalone functions

5. `src/pycmor/__init__.py` (+~5 lines)
   - Import accessors module (triggers registration)

6. `doc/index.rst` (+~2 lines)
   - Link to accessor documentation

### Totals

- **New code**: ~1150 lines
- **Modified code**: ~200 lines
- **Total implementation**: ~1350 lines

## Benefits

1. **Version-agnostic**: Works seamlessly with CMIP6 and CMIP7
2. **Flexible lookups**: Table-based (CMIP6), compound names (CMIP7), or manual
3. **Smart detection**: Auto-detect format when possible
4. **No CMIP dependency**: Can work without DataRequestVariable for basic operations
5. **Backward compatible**: Pipeline code unchanged
6. **Interactive-friendly**: Natural accessor pattern for notebooks
7. **Discoverable**: Tab-completion reveals available operations
8. **Future-proof**: Easy to extend for CMIP8+ if naming conventions change

## Risks & Mitigation

### Risk 1: Complex API with many optional parameters

**Mitigation**:
- Smart defaults that work for common cases
- Clear priority order documented
- Good error messages for ambiguous arguments
- Examples for each use case

### Risk 2: Confusion about which parameters to use (CMIP6 vs CMIP7)

**Mitigation**:
- Comprehensive documentation with version-specific examples
- Smart detection reduces need to know exact format
- Error messages guide users to correct parameters

### Risk 3: CMIP7 API dependency optional

**Mitigation**:
- Graceful degradation when CMIP7 API not available
- Clear error messages if CMIP7 features used without API
- Fallback to basic dimension mapping works without any CMIP context

### Risk 4: Maintenance burden of multiple entry points

**Mitigation**:
- Accessor is thin wrapper over existing functions
- Core logic remains in std_lib modules
- Pipeline and accessor paths converge quickly

## Future Enhancements (Out of Scope)

These features are NOT included in this implementation but could be added later:

1. **Method chaining**: `ds.pycmor.dims.map(...).coords.set_attributes()`
2. **Global CMIP version**: `pycmor.set_cmip_version("CMIP7")` to avoid repeating
3. **One-shot CMORization**: `ds.pycmor.cmipify("atmos.tas...")`
4. **Validation accessor**: `ds.pycmor.validate.check_cf_compliance()`
5. **Metadata accessor**: `ds.pycmor.metadata.get_variable_info(...)`
6. **Rename timefreq**: `ds.pycmor.time` instead of separate `ds.timefreq`
7. **CMIP8+ support**: When specifications released

## Testing Strategy

### Unit Tests

- Test each accessor method independently
- Mock DataRequest lookups
- Test all parameter combinations
- Error cases and edge cases

### Integration Tests

- Test with real CMIP6 tables
- Test with real CMIP7 metadata (if available)
- Test dimension mapping + coordinate attributes together
- Test with actual model output files

### Documentation Tests

- Doctest all examples in docstrings
- Verify examples in RST documentation work

## Implementation Order

Recommended implementation order to minimize dependencies:

1. **Phase 1**: Core infrastructure
   - Task 1: Create accessor module skeleton
   - Task 2: Add variable lookup helper
   - Tests for lookup logic

2. **Phase 2**: Coordinate attributes (simpler)
   - Task 3: Refactor coordinate_attributes.py
   - Task 5a: Implement CoordinateAccessor
   - Tests for coordinate accessor

3. **Phase 3**: Dimension mapping (more complex)
   - Task 4: Refactor dimension_mapping.py
   - Task 5b: Implement DimensionAccessor
   - Tests for dimension accessor

4. **Phase 4**: Documentation and integration
   - Task 6: Write documentation
   - Task 7: Complete test suite
   - Task 8: Integration updates

## Success Criteria

The implementation is successful if:

1. All tests pass (unit, integration, documentation)
2. Both CMIP6 and CMIP7 usage patterns work
3. Standalone mode (no CMIP tables) works
4. Pipeline usage remains unchanged
5. Documentation has examples for all use cases
6. Pre-commit checks pass
7. No performance regression in pipeline mode

## Open Questions

1. Should we add a default `cmor_version` config option that gets picked up automatically?
2. Should `variable_spec` smart detection be strict or permissive?
3. Should we validate CMIP7 compound names for correct format?
4. Should we cache DataRequestVariable lookups for performance?
5. Should we add a verbose mode for debugging dimension detection?

## Related Documentation

- Existing coordinate_attributes.rst
- Existing dimension_mapping.rst
- xarray accessor documentation: https://docs.xarray.dev/en/stable/internals/extending-xarray.html
- CMIP6 tables: https://github.com/PCMDI/cmip6-cmor-tables
- CMIP7 Data Request: https://github.com/CMIP-Data-Request/CMIP7_DReq_Software
