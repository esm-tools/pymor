# Accessor Merge Plan: future/accessors + tmp-accessor-coord-metadata

## Current State Analysis

### Future/Accessors Implementation (560 lines)
**Location**: `~/Code/worktree-checkouts/github.com/esm-tools/pycmor/future/accessors/src/pycmor/accessors.py`

**Features**:
- Single unified `.pycmor` accessor for both Dataset and DataArray
- **Time frequency operations** (delegates to TimeFrequencyAccessor):
  - `.resample_safe()` - Safe resampling with resolution validation
  - `.check_resolution()` - Check temporal resolution
  - `.infer_frequency()` - Infer frequency from time series
- **Full pipeline processing**:
  - `.process(variable, cmor_version='CMIP7', pipeline=None, **kwargs)`
  - CMIP6/7 variable lookup via factory pattern
  - Config file integration (inherit defaults)
  - TableLocator integration (5-level priority chain)
  - Automatic Rule construction from kwargs
- **Lazy loading** of specialized accessors
- Comprehensive error handling

### Tmp-Accessor Implementation (650 lines)
**Location**: `src/pycmor/core/accessor.py`

**Features**:
- `.pycmor` main accessor with **sub-accessor architecture**:
  - `.pycmor.coords` - Coordinate attribute operations
  - `.pycmor.dims` - Dimension mapping operations
- **Coordinate operations** (CoordinateAccessor):
  - `.set_attributes()` - Apply CF-compliant metadata
  - `.get_metadata()` - Query coordinate metadata
  - `.list_recognized()` - List known coordinates
  - `.validate()` - Validate existing attributes
- **Dimension operations** (DimensionAccessor):
  - `.detect_types()` - Identify dimension types
  - `.map_to_cmip()` - Map dimensions with multiple modes
  - `.create_mapping()` - Create mapping without applying
  - `.apply_mapping()` - Apply existing mapping
- **Standalone operation** - Works without full pipeline/Rule setup
- **Flexible operation modes**:
  - CMIP6: table + variable
  - CMIP7: compound_name
  - Smart: variable_spec (auto-detect)
  - Standalone: target_dimensions (no CMIP tables)

## Key Observations

### Complementary Functionality
The two implementations are **highly complementary**, not competing:
- **Future**: High-level pipeline orchestration, config integration
- **Tmp**: Low-level coordinate/dimension manipulation, exploratory analysis

### Architectural Differences
- **Future**: Flat accessor with delegation pattern
- **Tmp**: Hierarchical accessor with sub-accessor pattern

### Common Ground
- Both register `.pycmor` accessor
- Both support CMIP6/7
- Both use lazy loading (future for timefreq, tmp could adopt)
- Both work on Dataset and DataArray

## Proposed Unified Architecture

### Directory Structure
```
src/pycmor/xarray/
├── __init__.py              # Registration, exports, main accessor
├── coords.py                # Coordinate operations (from tmp)
├── dims.py                  # Dimension operations (from tmp)
├── pipeline.py              # Pipeline operations (from future)
├── timefreq.py              # Time frequency operations (from future)
└── utils.py                 # Shared utilities (config builders, lookups)
```

### Main Accessor: `xarray/__init__.py`
```python
"""
Unified pycmor xarray accessor.

Provides access to all pycmor functionality via a single .pycmor namespace:
- .pycmor.coords - Coordinate attribute operations
- .pycmor.dims - Dimension mapping operations
- .pycmor.process() - Full pipeline processing
- .pycmor.resample_safe() - Time frequency operations
"""

from xarray import register_dataarray_accessor, register_dataset_accessor

@register_dataset_accessor("pycmor")
class PycmorAccessor:
    """Unified pycmor accessor for xarray Datasets."""

    def __init__(self, xarray_obj):
        self._obj = xarray_obj
        # Lazy initialization
        self._coords_accessor = None
        self._dims_accessor = None
        self._timefreq_accessor = None

    # Sub-accessor properties (lazy loaded)
    @property
    def coords(self):
        """Coordinate attribute operations."""
        if self._coords_accessor is None:
            from .coords import CoordinateAccessor
            self._coords_accessor = CoordinateAccessor(self._obj)
        return self._coords_accessor

    @property
    def dims(self):
        """Dimension mapping operations."""
        if self._dims_accessor is None:
            from .dims import DimensionAccessor
            self._dims_accessor = DimensionAccessor(self._obj)
        return self._dims_accessor

    # Pipeline methods (from future/accessors)
    def process(self, variable=None, cmor_version="CMIP7", pipeline=None, **kwargs):
        """Process data through pycmor pipeline."""
        from .pipeline import process_data
        return process_data(self._obj, variable, cmor_version, pipeline, **kwargs)

    # Time frequency methods (from future/accessors)
    def resample_safe(self, *args, **kwargs):
        """Resample with temporal resolution validation."""
        if self._timefreq_accessor is None:
            from .timefreq import TimeFrequencyAccessor
            self._timefreq_accessor = TimeFrequencyAccessor(self._obj)
        return self._timefreq_accessor.resample_safe(*args, **kwargs)

    def check_resolution(self, *args, **kwargs):
        """Check temporal resolution."""
        if self._timefreq_accessor is None:
            from .timefreq import TimeFrequencyAccessor
            self._timefreq_accessor = TimeFrequencyAccessor(self._obj)
        return self._timefreq_accessor.check_resolution(*args, **kwargs)

    def infer_frequency(self, *args, **kwargs):
        """Infer frequency from time series."""
        if self._timefreq_accessor is None:
            from .timefreq import TimeFrequencyAccessor
            self._timefreq_accessor = TimeFrequencyAccessor(self._obj)
        return self._timefreq_accessor.infer_frequency(*args, **kwargs)


@register_dataarray_accessor("pycmor")
class PycmorDataArrayAccessor(PycmorAccessor):
    """Unified pycmor accessor for xarray DataArrays."""
    pass
```

## Merge Strategy: Phased Approach

### Phase 1: Structure Setup (Low Risk)
**Goal**: Create new `xarray/` submodule without breaking existing code

**Steps**:
1. Create `src/pycmor/xarray/` directory
2. Create `xarray/__init__.py` with basic accessor registration
3. Move coordinate/dimension code from tmp to new structure:
   - `core/accessor.py` → split into `xarray/coords.py` + `xarray/dims.py`
   - Extract shared utilities → `xarray/utils.py`
4. Update imports in `src/pycmor/__init__.py`:
   ```python
   # Old: from .core import accessor
   # New: from .xarray import accessor  # Or just import .xarray
   ```
5. **Test**: Verify basic accessor registration works

**Time**: 2-3 hours
**Risk**: Low (new code, doesn't touch existing)

### Phase 2: Integrate Pipeline Operations (Medium Risk)
**Goal**: Add `.process()` method from future/accessors

**Steps**:
1. Create `xarray/pipeline.py` with `process_data()` function
2. Port logic from future/accessors `.process()` method:
   - Variable lookup with factory pattern
   - Config integration
   - Rule construction
   - Pipeline execution
3. Add to main accessor as method delegation
4. **Test**: Verify `.process()` works with CMIP6/7

**Dependencies**:
- Needs factory pattern from future (or adapt to current codebase)
- Needs config.get_inherit_section() (may need to add)

**Time**: 4-6 hours
**Risk**: Medium (touches core Rule/Pipeline code)

### Phase 3: Add Time Frequency Operations (Low Risk)
**Goal**: Add timefreq methods from future/accessors

**Steps**:
1. Verify `core/infer_freq.py` has TimeFrequencyAccessor
2. Create `xarray/timefreq.py` as thin wrapper/import
3. Add delegation methods to main accessor
4. **Test**: Verify time operations work

**Time**: 1-2 hours
**Risk**: Low (timefreq already exists, just exposing it)

### Phase 4: Documentation & Tests (Critical)
**Goal**: Unified documentation and comprehensive tests

**Steps**:
1. Merge documentation:
   - Combine `doc/xarray_accessors.rst` (tmp) with future docs
   - Add pipeline examples
   - Add timefreq examples
2. Merge test suites:
   - Keep all tests from `test_xarray_accessors.py`
   - Add tests from future/accessors
   - Add integration tests (coords + dims + process)
3. Update API reference
4. **Test**: Full test suite passes

**Time**: 4-5 hours
**Risk**: Low (but critical for quality)

### Phase 5: Deprecation & Cleanup (Optional)
**Goal**: Clean up old accessor locations

**Steps**:
1. Deprecate old `core/accessor.py` (if moved entirely)
2. Update all imports across codebase
3. Update CI/CD if needed
4. **Test**: Ensure no broken imports

**Time**: 1-2 hours
**Risk**: Low (with good testing)

## Naming Convention Recommendations

### Option A: `xarray/` submodule (RECOMMENDED)
**Structure**:
```
src/pycmor/xarray/
├── __init__.py        # Main PycmorAccessor
├── coords.py          # CoordinateAccessor
├── dims.py            # DimensionAccessor
├── pipeline.py        # Pipeline processing
├── timefreq.py        # Time frequency ops
└── utils.py           # Shared utilities
```

**Import**:
```python
import pycmor
ds.pycmor.coords.set_attributes()
ds.pycmor.dims.map_to_cmip()
ds.pycmor.process('tas')
```

**Pros**:
- Clear namespace separation (`xarray` vs `core`, `std_lib`, etc.)
- Easy to find all accessor code
- Matches Python conventions (submodule for related functionality)
- Easy to document: "All xarray extensions are in `pycmor.xarray`"

**Cons**:
- Requires directory restructure
- More import depth

### Option B: Flat in `core/` (Alternative)
**Structure**:
```
src/pycmor/core/
├── accessor.py              # Main accessor
├── accessor_coords.py       # Coordinate operations
├── accessor_dims.py         # Dimension operations
├── accessor_pipeline.py     # Pipeline operations
└── accessor_timefreq.py     # Time frequency operations
```

**Pros**:
- Minimal restructure
- All in existing `core/` module

**Cons**:
- File proliferation in `core/`
- Less clear organization
- Mixes accessor code with core Rule/Pipeline/Config code

### Option C: Separate `accessors/` submodule (Alternative)
Same as Option A but `accessors/` instead of `xarray/`

**Pros/Cons**: Similar to Option A, slightly more explicit name

## Recommended Naming: Option A with `xarray/`

**Rationale**:
1. **Clarity**: Immediately obvious these are xarray extensions
2. **Standards**: Common pattern in ecosystem (pandas has `.str`, `.dt` accessors; cf-xarray uses `.cf`)
3. **Future-proof**: Easy to add more xarray-related utilities here
4. **Discoverability**: Users know where to look for xarray functionality
5. **Both teams agree**: Creates common ground for future collaboration

## Migration Path for Users

### Backward Compatibility Strategy

**Phase 1-3** (During development):
- Keep both old and new locations working
- Add deprecation warnings:
  ```python
  # In old core/accessor.py
  import warnings
  warnings.warn(
      "Importing from pycmor.core.accessor is deprecated. "
      "Use pycmor.xarray instead.",
      DeprecationWarning,
      stacklevel=2
  )
  ```

**Phase 4** (After merge):
- New code uses `xarray/` exclusively
- Old imports still work but warn
- Documentation shows new patterns

**Phase 5** (Next release):
- Remove old locations
- Update all internal code
- Breaking change announcement

### User Migration Examples

**Old way** (future/accessors):
```python
import pycmor
ds.pycmor.process('tas', cmor_version='CMIP6')
```

**New way** (after merge):
```python
import pycmor  # Same!
ds.pycmor.process('tas', cmor_version='CMIP6')  # Same!
ds.pycmor.coords.set_attributes()  # NEW!
ds.pycmor.dims.detect_types()  # NEW!
```

**Key point**: Existing `.process()` calls continue working unchanged!

## Conflict Resolution

### Potential Conflicts

1. **Both register `.pycmor`**: RESOLVED - Unified accessor
2. **Different architectural patterns**: RESOLVED - Combine hierarchical sub-accessors with flat methods
3. **Naming conventions**: RESOLVED - Use `xarray/` submodule

### Design Decisions

**Q**: Flat accessor (future style) vs hierarchical (tmp style)?
**A**: **Hybrid** - Use hierarchical for logical grouping (coords, dims) but keep convenience methods at top level (process, resample_safe)

**Q**: Where do helper functions go?
**A**: `xarray/utils.py` for shared code (config builders, variable lookups, etc.)

**Q**: How to handle lazy loading?
**A**: All sub-accessors lazy loaded on first access

**Q**: How to handle Rule-less operation (tmp) vs Rule-full (future)?
**A**: Support both - coords/dims work standalone, process() creates Rule internally

## Testing Strategy

### Test Categories

1. **Unit Tests** (per module):
   - `test_xarray_coords.py` - Coordinate operations
   - `test_xarray_dims.py` - Dimension operations
   - `test_xarray_pipeline.py` - Pipeline processing
   - `test_xarray_timefreq.py` - Time frequency operations

2. **Integration Tests**:
   - Test accessor registration
   - Test combined workflows (dims + coords + process)
   - Test CMIP6 and CMIP7 paths
   - Test standalone and Rule-based operation

3. **Regression Tests**:
   - Import all examples from future/accessors docs
   - Import all examples from tmp docs
   - Verify all still work

### CI/CD Updates

Add to `.github/workflows/CI-test.yaml`:
```yaml
- name: Test xarray accessors
  run: |
    pytest tests/unit/test_xarray_*.py -v
    pytest tests/integration/test_accessor_*.py -v
```

## Documentation Strategy

### New Documentation Structure

```
doc/
├── xarray_integration.rst          # Overview of all accessor features
├── xarray_coordinate_ops.rst       # Detailed coordinate operations
├── xarray_dimension_ops.rst        # Detailed dimension operations
├── xarray_pipeline_ops.rst         # Pipeline processing
├── xarray_timefreq_ops.rst         # Time frequency operations
└── xarray_cookbook.rst             # Common recipes combining features
```

### Migration Guide

Create `doc/accessor_migration.rst`:
- How to migrate from old patterns
- What changed
- What's new
- Deprecation timeline

## Timeline & Effort Estimate

| Phase | Tasks | Time | Risk | Blocker |
|-------|-------|------|------|---------|
| Phase 1 | Structure setup | 2-3h | Low | None |
| Phase 2 | Pipeline integration | 4-6h | Medium | Factory pattern |
| Phase 3 | Timefreq integration | 1-2h | Low | None |
| Phase 4 | Documentation & tests | 4-5h | Low | None |
| Phase 5 | Cleanup (optional) | 1-2h | Low | None |
| **Total** | | **12-18h** | | |

**Recommended**: Spread over 2-3 work sessions

## Success Criteria

Merge is successful when:
1. ✅ All accessor functionality from both projects available
2. ✅ `.pycmor` namespace works for Dataset and DataArray
3. ✅ CMIP6 and CMIP7 workflows both supported
4. ✅ Standalone (no Rule) operations work
5. ✅ Pipeline-based operations work
6. ✅ All tests pass (unit + integration)
7. ✅ Documentation complete and accurate
8. ✅ No breaking changes for existing future/accessor users
9. ✅ Pre-commit checks pass
10. ✅ Example notebooks run successfully

## Open Questions / Decisions Needed

1. **Factory pattern**: Does tmp codebase have factory pattern for DataRequest/TableLocator?
   - If NO: Simplify future's `.process()` to use simpler lookup
   - If YES: Use existing factory pattern

2. **Config inheritance**: Does tmp codebase have `config.get_inherit_section()`?
   - If NO: Add this method to PycmorConfigManager
   - If YES: Use as-is

3. **TableLocator**: Does tmp have 5-level priority chain?
   - Check compatibility with future's implementation

4. **Import location**: Should users import from:
   - `from pycmor import xarray` (explicit)
   - Just `import pycmor` (implicit, accessor auto-registers)
   - Recommendation: **Both work**, prefer implicit

5. **Deprecation timeline**: When to remove old accessor locations?
   - Recommendation: 2 minor releases (warn in N.x, remove in N.x+2)

## Next Steps (Immediate)

1. **Get consensus** on `xarray/` submodule naming ✅
2. **Create Phase 1 branch**: `feat/xarray-accessor-merge`
3. **Implement Phase 1**: Create basic structure
4. **Test Phase 1**: Verify no breakage
5. **Review & iterate**: Get feedback before Phase 2

## Notes

- Both implementations are high quality and well-tested
- Merge adds value without removing anything
- Users get best of both worlds: granular ops + pipeline processing
- Architecture is extensible for future additions (validation accessor, metadata accessor, etc.)
