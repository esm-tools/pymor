# PyCMOR Xarray Accessor Implementation

## What we're building
An xarray accessor that lets you run CMOR pipelines directly on Dataset/DataArray objects. The approach is dead simple - just a `process()` method that takes a pipeline and creates a minimal Rule object on the fly. No config loading, no state management, just a thin wrapper that lets you go from xarray object to CMORized output.

## What needs to work
- Register as `.pycmor` on both Dataset and DataArray
- One method: `process(identifier=None, compound_name=None, cmor_variable=None, cmor_version="CMIP7", data_request_variable=None, pipeline=None, **rule_kwargs)`
- Create a Rule from kwargs (with DataRequestVariable if provided), run the pipeline on the data
- Pass `(data, rule)` tuples to pipelines (data = the xarray object)
- First positional arg interprets based on CMIP version (compound_name for CMIP7, cmor_variable for CMIP6)
- Actually helpful error messages when things break

## Constraints
- xarray >= 0.19.0
- Don't break existing pycmor usage
- Don't duplicate logic that's already in pipelines
- Use pycmor's config infrastructure, don't roll our own

## Implementation

Just one simple class with one method:

```python
@xr.register_dataset_accessor("pycmor")
@xr.register_dataarray_accessor("pycmor")
class PyCMORAccessor:
    def __init__(self, xarray_obj):
        self._obj = xarray_obj

    def process(self, pipeline=None, **rule_kwargs):
        """
        Run a pipeline on this data.

        Creates a Rule from kwargs and runs the pipeline.
        If no pipeline provided, tries to use DefaultPipeline.
        """
        # Create minimal rule from kwargs
        rule = Rule.from_dict(rule_kwargs)

        # Get pipeline
        if pipeline is None:
            pipeline = DefaultPipeline()
        elif isinstance(pipeline, str):
            pipeline = Pipeline.from_name(pipeline)

        # Run it
        return pipeline.run(self._obj, rule)
```

That's it. No phases, no complexity, just works.

## Files to create
1. `src/pycmor/accessor.py` - main implementation (maybe 50 lines?)
2. `tests/test_accessor.py` - tests (basic registration + pipeline run tests)

## What the final API should look like

```python
import xarray as xr
import pycmor

ds = xr.open_mfdataset("model_output_*.nc")

# Simplest case - CMIP7 compound name (default)
ds_cmor = ds.pycmor.process("atmos.tas.tavg-h2m-hxy-u.mon.GLB")

# CMIP6 - simple variable name
ds_cmor = ds.pycmor.process("tas", cmor_version="CMIP6")

# With pipeline
ds_cmor = ds.pycmor.process(
    "ocean.tos.tavg-u-hxy-u.mon.GLB",
    pipeline="RegriddingPipeline"
)

# Explicit kwargs for clarity
ds_cmor = ds.pycmor.process(
    compound_name="atmos.tas.tavg-h2m-hxy-u.mon.GLB"
)
ds_cmor = ds.pycmor.process(
    cmor_variable="tas",
    cmor_version="CMIP6"
)

# Full control with rule attributes
ds_cmor = ds.pycmor.process(
    "ocean.tos.tavg-u-hxy-u.mon.GLB",
    pipeline=RegriddingPipeline(),
    source_id="FESOM2",
    experiment_id="historical",
    variant_label="r1i1p1f1"
)

# Pre-loaded DataRequestVariable
from pycmor.data_request.collection import CMIP7DataRequest
dr = CMIP7DataRequest.from_vendored_json()
drv = dr.variables["atmos.tas.tavg-h2m-hxy-u.mon.GLB"]
ds_cmor = ds.pycmor.process(
    "atmos.tas.tavg-h2m-hxy-u.mon.GLB",
    data_request_variable=drv
)
```

Just one method. Straightforward. Gets out of your way.

Note: The first argument interprets based on CMIP version. With CMIP7 (the default), it's treated as a compound_name like "atmos.tas.tavg-h2m-hxy-u.mon.GLB". With CMIP6, it's treated as a simple cmor_variable like "tas". You can always be explicit by using the `compound_name=` or `cmor_variable=` kwargs.

## Done when
- Tests pass
- Works with both Dataset and DataArray
- Error messages are useful
- Doesn't break existing pycmor functionality
