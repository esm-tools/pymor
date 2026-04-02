# CMIP7 Data Request - Quick Start Guide

## CMIP7 Architecture

**Key Difference from CMIP6**: CMIP7 uses **compound names** instead of tables to identify variables.

- **CMIP6**: `table.variable` (e.g., `Omon.tos`)
- **CMIP7**: `realm.variable.branding.frequency.region` (e.g., `ocean.tos.tavg-u-hxy-sea.mon.GLB`)

The compound name structure provides:
- **realm**: Component (ocean, atmos, land, etc.)
- **variable**: Physical parameter (tos, tas, etc.)
- **branding**: Processing method (tavg-u-hxy-sea = time-averaged, unstaggered, horizontal mean over sea)
- **frequency**: Output frequency (mon, day, 3hr, etc.)
- **region**: Spatial region (GLB = global)

## Installation

```bash
cd /path/to/pymorize
git clone https://github.com/CMIP-Data-Request/CMIP7_DReq_Software.git
```

## 30-Second Start

```python
from pycmor.data_request import CMIP7DataRequest

# Load CMIP7 metadata (compound name based)
dreq = CMIP7DataRequest.from_json_file("path/to/metadata.json")

# Variables are indexed by compound name
var = dreq.variables["ocean.tos.tavg-u-hxy-sea.mon.GLB"]
print(var.out_name)  # "tos"
print(var.frequency)  # "mon"
```

## Common Tasks

### Using Compound Names in Configuration

**CMIP7 rules use compound names, not table.variable format**:

```yaml
general:
  name: "my-cmip7-run"
  cmor_version: "CMIP7"
  mip: "CMIP"
  CMIP7_DReq_metadata: "/path/to/metadata.json"

rules:
  - name: sea_surface_temp
    compound_name: ocean.tos.tavg-u-hxy-sea.mon.GLB  # Full compound name
    model_variable: sst
    inputs:
      - path: /data/ocean
        pattern: sst_*.nc
    source_id: MY-MODEL
    institution_id: MY-INSTITUTE
    # ... additional configuration
```

**Important**: Use the **full compound name** for exact matching. The system compares the entire compound name, preserving branding, frequency, and region information.

### Loading CMIP7 Metadata

```python
from pycmor.data_request import CMIP7DataRequest

# From JSON file
dreq = CMIP7DataRequest.from_json_file("metadata.json")

# From directory (finds metadata.json automatically)
dreq = CMIP7DataRequest.from_directory("/path/to/cmip7_metadata/")

# Variables indexed by compound name
print(f"Loaded {len(dreq.variables)} variables")
print(list(dreq.variables.keys())[:5])  # Show first 5 compound names
```

### Querying Variables

```python
# Get specific variable by compound name
var = dreq.variables.get("ocean.tos.tavg-u-hxy-sea.mon.GLB")
if var:
    print(f"Variable: {var.out_name}")
    print(f"Frequency: {var.frequency}")
    print(f"Units: {var.units}")
    print(f"Compound name: {var.variable_id}")

# Find all ocean monthly variables
ocean_mon = {
    name: var for name, var in dreq.variables.items()
    if name.startswith("ocean.") and ".mon." in name
}
print(f"Found {len(ocean_mon)} ocean monthly variables")

# Find all variants of a variable (different branding/frequency)
tos_variants = {
    name: var for name, var in dreq.variables.items()
    if name.startswith("ocean.tos.")
}
for name in sorted(tos_variants.keys()):
    print(f"  {name}")
```

### Check Version Compatibility

```python
from pycmor.data_request import CMIP7DataRequestWrapper

wrapper = CMIP7DataRequestWrapper()
wrapper.retrieve_content("v1.2")
if wrapper.check_version_compatibility():
    print("Compatible!")
```

## Recommended Versions

✅ **Use these**: v1.0, v1.1, v1.2
⚠️ **Avoid these**: v1.2.2.1, v1.2.2.2 (incompatible)

## Import Cheat Sheet

```python
# Quick access
from pycmor.data_request import get_cmip7_data_request

# Full wrapper
from pycmor.data_request import CMIP7DataRequestWrapper

# Built-in classes (no external repo needed)
from pycmor.data_request import CMIP7DataRequest

# Check availability
from pycmor.data_request import CMIP7_DREQ_AVAILABLE
```

## Distinguishing Variable Variants

CMIP7 allows multiple variants of the same physical variable with different processing:

```python
# Different time averaging (tavg vs tpt = time point)
var1 = dreq.variables["ocean.tos.tavg-u-hxy-sea.mon.GLB"]
var2 = dreq.variables["ocean.tos.tpt-u-hxy-sea.3hr.GLB"]

# Same physical variable (tos), different:
# - Branding: tavg-u-hxy-sea vs tpt-u-hxy-sea
# - Frequency: mon vs 3hr
# - These are treated as DISTINCT variables in CMIP7
```

## Troubleshooting

**Problem**: Rule has no matching data_request_variables
**Solution**: Check that your `compound_name` exactly matches a variable in the metadata:
```bash
# Verify compound name exists
grep "ocean.tos.tavg-u-hxy-sea.mon.GLB" metadata.json
```

**Problem**: `Data request has 0 variables` despite valid metadata
**Solution**: Ensure `CMIP7_DReq_metadata` path is correct in your config:
```yaml
general:
  CMIP7_DReq_metadata: "/absolute/path/to/metadata.json"  # Use absolute path
```

**Problem**: Metadata file doesn't work
**Solution**: CMIP7 metadata **no longer requires** `cmip6_table` field. Pure CMIP7 metadata should work. If it doesn't, check for JSON formatting issues.

**Problem**: Multiple variants of variable all matching
**Solution**: With the new architecture, matching is **exact** - only the rule with the exact compound name will match. Different branding/frequency/region are distinct variables.

**Problem**: Want to match multiple variants with one rule
**Solution**: Create separate rules for each variant you want to process, each with its specific compound name.

## Full Documentation

- **Usage Guide**: `docs/cmip7_wrapper_usage.md`
- **Import Examples**: `docs/cmip7_import_examples.md`
- **Summary**: `CMIP7_WRAPPER_SUMMARY.md`

## Support

- **GitHub Issues**: [CMIP7_DReq_Software Issues](https://github.com/CMIP-Data-Request/CMIP7_DReq_Software/issues)
- **Discussions**: [CMIP7_DReq_Software Discussions](https://github.com/CMIP-Data-Request/CMIP7_DReq_Software/discussions)
