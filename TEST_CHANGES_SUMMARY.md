# Test Accessor Changes Summary

## Overview
Rewrote `tests/unit/test_accessors.py` to use the new simplified `process()` API instead of the old `load_config()` + `run()` pattern.

## API Change
- **Old API**: `ds.pycmor.load_config("config.yaml").run("tas")`
- **New API**: `ds.pycmor.process(cmor_variable="tas", pipeline=my_pipeline)`

## Changes Made

### 1. Updated Fixtures (Lines 44-93)
- **Removed**: Config-based fixtures (`minimal_pipeline_config`, `multi_pipeline_config`, `config_with_inherit`, `temp_config_file`)
- **Added**: Simple pipeline fixtures:
  - `simple_pipeline`: Single step pipeline (multiply by 2)
  - `multi_step_pipeline`: Multi-step pipeline (multiply by 2, then add 10)
  - `rule_accessing_pipeline`: Pipeline that accesses and applies rule attributes

### 2. Added Mock Pipeline Steps (Lines 45-63)
- `mock_step_multiply(data, rule)`: Multiplies data by 2
- `mock_step_add(data, rule)`: Adds 10 to data
- `mock_step_with_rule_access(data, rule)`: Accesses rule attributes and adds them to data.attrs

### 3. Kept Time Frequency Tests (Lines 96-296)
- `TestPycmorDataArrayAccessor`: Tests for time frequency methods on DataArrays (unchanged)
- `TestPycmorDatasetAccessor`: Tests for time frequency methods on Datasets (unchanged)
- These test the delegation to specialized `timefreq` accessor

### 4. Created New Process API Tests

#### TestProcessMethodDataArray (Lines 299-418)
Tests the simplified `process()` API for DataArrays:
- `test_process_basic`: Basic processing with default pipeline
- `test_process_with_pipeline_name`: Using pipeline name string
- `test_process_with_pipeline_class`: Using Pipeline class
- `test_process_with_pipeline_instance`: Using pipeline instance
- `test_process_with_rule_kwargs`: Passing rule attributes as kwargs
- `test_process_returns_correct_type`: Ensures DataArray returns DataArray
- `test_process_missing_cmor_variable`: Error handling for missing cmor_variable
- `test_process_missing_pipeline`: Error handling for missing pipeline
- `test_process_with_empty_cmor_variable`: Edge case testing
- `test_process_multiple_rule_attributes`: Multiple kwargs handling

#### TestProcessMethodDataset (Lines 420-537)
Tests the simplified `process()` API for Datasets:
- `test_process_basic`: Basic processing with default pipeline
- `test_process_with_pipeline_name`: Using pipeline name string
- `test_process_with_pipeline_class`: Using Pipeline class
- `test_process_with_pipeline_instance`: Using pipeline instance
- `test_process_with_rule_kwargs`: Passing rule attributes as kwargs
- `test_process_returns_correct_type`: Ensures Dataset returns Dataset
- `test_process_missing_cmor_variable`: Error handling for missing cmor_variable
- `test_process_missing_pipeline`: Error handling for missing pipeline
- `test_process_preserves_data_variables`: Ensures all data variables preserved
- `test_process_multiple_variables`: Processing with multiple variables

### 5. Updated Registration Tests (Lines 539-569)
- `TestAccessorRegistration`: Simplified to focus on accessor availability
- Added `test_process_method_exists`: Verifies `process()` method is available

### 6. Removed Old Tests
- **Removed**: All `TestPipelineAccessorDataArray` tests (load_config/run pattern)
- **Removed**: All `TestPipelineAccessorDataset` tests (load_config/run pattern)
- **Removed**: `TestAccessorInteroperability` class (mostly redundant)
- **Removed**: Config loading/validation tests
- **Removed**: `list_pipelines()` and `list_rules()` tests
- **Removed**: Method chaining tests for old API

## Test Count Summary
- **Before**: ~100+ tests across 8 test classes
- **After**: ~70 tests across 5 test classes
- **File size**: 739 lines → 570 lines (23% reduction)

## Key Testing Patterns

### Simple Process Call
```python
result = data.pycmor.process(
    cmor_variable="tas",
    pipeline=simple_pipeline
)
```

### Process with Rule Attributes
```python
result = data.pycmor.process(
    cmor_variable="tas",
    pipeline=pipeline,
    experiment_id="piControl",
    source_id="TEST-MODEL",
    custom_attr="value"
)
```

### Process with Multi-Step Pipeline
```python
result = data.pycmor.process(
    cmor_variable="tas",
    pipeline=multi_step_pipeline  # Applies multiple transformations
)
```

## Benefits of New API
1. **Simpler**: No config loading step required
2. **Stateless**: No internal state management in accessor
3. **Direct**: Pass pipeline and rule attributes directly
4. **Flexible**: Can use pipeline name, class, or instance
5. **Type-safe**: Returns same type as input (DataArray → DataArray, Dataset → Dataset)

## Next Steps
The tests are written for the new `process()` API. To make them pass:
1. Implement `process()` method in `PycmorDataArrayAccessor`
2. Implement `process()` method in `PycmorDatasetAccessor`
3. Both should accept: `cmor_variable` (str), `pipeline` (Pipeline), and `**rule_kwargs`
4. Create a Rule object from cmor_variable and kwargs
5. Run the pipeline on the data with the rule
6. Return the processed result
