# CMIP7 DataRequest Implementation Relies on CMIP6 Backward Compatibility Fields

## Summary

The current CMIP7 implementation in pycmor forces CMIP7 data into CMIP6's table-based architecture rather than using CMIP7's native compound name structure. This creates fragility, requires CMIP6 backward compatibility fields to be present in metadata, and prevents proper use of CMIP7's enhanced variable identification system.

## Background

### CMIP6 Architecture
- **Table-based**: Variables organized by table (e.g., `Omon`, `Amon`, `3hr`)
- **Variable identification**: `table_id.variable_name` (e.g., `Omon.tos`)
- **Hierarchical structure**: Tables → Variables

### CMIP7 Architecture
- **Flat compound name structure**: `realm.variable.branding.frequency.region`
- **Example**: `ocean.tos.tavg-u-hxy-sea.mon.GLB`
- **Enhanced identification**: Branding and region provide precise variable disambiguation
- **No table concept**: Variables identified directly by compound name

## Problems

### 1. CMIP6 Table IDs Required for CMIP7 DataRequest Loading

**Location**: `src/pycmor/data_request/collection.py:73-76`

```python
# Extract table IDs from cmip6_table field, not compound name first part
table_ids = set(
    v.get("cmip6_table") for v in data["Compound Name"].values() if v.get("cmip6_table")
)
```

**Issue**: The code requires `cmip6_table` field (values like `Omon`, `3hr`, `Amon`) to organize CMIP7 variables, even though CMIP7 doesn't use this concept natively.

**Impact**: 
- If metadata lacks `cmip6_table` fields, DataRequest loads **0 variables** (silently fails)
- Forces dependency on CMIP6 backward compatibility fields
- Prevents pure CMIP7 metadata files from working

### 2. Table-Based Variable Organization for CMIP7

**Location**: `src/pycmor/data_request/table.py:671-681`

```python
def from_all_var_info(cls, table_name: str, all_var_info: dict = None):
    # ...
    variables = []
    for var_name, var_dict in all_var_info["Compound Name"].items():
        if var_dict.get("cmip6_table") == table_name:
            variables.append(CMIP7DataRequestVariable.from_dict(var_dict))
    return cls(header, variables)
```

**Issue**: CMIP7 variables are filtered and grouped by CMIP6 `table_name` (`Omon`, `3hr`, etc.), creating artificial table boundaries that don't exist in CMIP7.

**Impact**:
- Mismatches CMIP7's conceptual model
- Variables with same physical meaning but different `cmip6_table` values are separated
- Table headers become meaningless for CMIP7 (they're CMIP6 constructs)

### 3. Variable Matching Extracts Only Variable Name, Losing Context

**Location**: `src/pycmor/core/cmorizer.py:475-481`

```python
# Both are compound names, extract variable parts for comparison
rule_parts = rule_value.split(".")
drv_parts = str(drv_value).split(".")
rule_var = rule_parts[1] if len(rule_parts) >= 2 else rule_value
drv_var = drv_parts[1] if len(drv_parts) >= 2 else drv_value
```

**Issue**: The matching logic extracts only the variable name (second element) from compound names, discarding branding, frequency, and region information.

**Example**:
- User config: `ocean.tos.tavg-u-hxy-sea.mon.GLB`
- Extracted for matching: `tos`
- Loses: `tavg-u-hxy-sea` (branding), `mon` (frequency), `GLB` (region)

**Impact**:
- Multiple CMIP7 variants of same variable (e.g., `ocean.tos.tavg-u-hxy-sea.mon.GLB` vs `ocean.tos.tpt-u-hxy-sea.3hr.GLB`) become ambiguous
- Can't distinguish between different time averaging or spatial selections
- Defeats purpose of CMIP7's enhanced identification

### 4. Variable ID Property Returns Wrong Type for Matching

**Location**: `src/pycmor/data_request/variable.py:600-604`

```python
@property
def variable_id(self) -> str:
    """For CMIP7, return compound name as variable identifier."""
    if hasattr(self, "_cmip7_compound_name") and self._cmip7_compound_name:
        return self._cmip7_compound_name
    return self.name  # Fallback to short name
```

**Issue**: `variable_id` returns the full compound name (correct), but matching logic then extracts just the variable name part (wrong), creating a mismatch between what's stored and what's compared.

### 5. Global Attributes Use CMIP6 Field Names

**Location**: `src/pycmor/std_lib/global_attributes.py:466-469`

```python
# Check if drv is a dict or object
if isinstance(self.drv, dict):
    table_id = self.drv.get("cmip6_table", None)
else:
    table_id = getattr(self.drv, "cmip6_table", None)
```

**Issue**: Output file attributes reference `cmip6_table` even for CMIP7 files.

## Reproduction

### What's Fixed in This Branch vs. What Remains

**This branch (`fix/cmip7-use-metadata-not-cmip6-tables`) fixes**:
- ✅ Silent failure (now warns when rules have no matching variables)
- ✅ `CMIP7_DReq_metadata` config being ignored
- ✅ `cmip6_cmor_table` key mismatch causing 0 variables
- ✅ Table ID extraction mismatch

**Architectural issues that REMAIN**:
- ❌ Still requires `cmip6_table` field in metadata (CMIP6 dependency)
- ❌ Still organizes variables by CMIP6 tables (not compound names)
- ❌ Still extracts only variable name for matching (loses branding/frequency/region)
- ❌ Still forces CMIP7 into CMIP6's table architecture

### How the Bug Manifested (on `main` branch, commit 8e3d6e4)

1. **Create minimal CMIP7 config with user-specified metadata**

```yaml
# awiesm3_minimal_tos.yaml
general:
  name: "awiesm3-minimal-tos"
  cmor_version: "CMIP7"
  mip: "CMIP"
  CMIP7_DReq_metadata: "/home/a/a270092/.cache/pycmor/cmip7_metadata/v1.2.2.2/metadata.json"

rules:
  - name: tos_1350
    inputs:
      - path: /path/to/fesom/outdata
        pattern: sst.fesom.1350.nc
    compound_name: ocean.tos.tavg-u-hxy-sea.mon.GLB
    model_variable: sst
    source_id: AWI-ESM-3
    institution_id: AWI
    # ... mesh config, etc.
```

2. **Run cmorization**

```bash
$ pycmor process awiesm3_minimal_tos.yaml
```

3. **Observe silent failure**

```
Using packaged cmip7-tables: /path/to/pycmor/src/pycmor/data/cmip7
Using user-specified cmip7_metadata: /home/a/a270092/.cache/pycmor/cmip7_metadata/v1.2.2.2/metadata.json
Loaded metadata for 1974 variables

# ... later in processing ...

Beginning flow run 'daft-seriema' for flow 'CMORizer Process'
Finished in state Completed()
```

**Result**: Completes in ~1 second with no output files. Rule silently dropped.

### Root Cause Discovery

**Log inspection reveals**:
```
Data request has 1134 variables  # Using packaged tables!
```

But user specified metadata with **1974 variables**.

**Issue 1**: `CMIP7_DReq_metadata` config ignored, loads from packaged tables instead.

**After fixing DataRequest loading** (use `CMIP7_DReq_metadata` path):
```
Data request has 0 variables
```

**Issue 2**: Changed `cmip6_cmor_table` → `cmip6_table` (key mismatch in code).

**After fixing key name**:
```
Data request has 0 variables  # Still broken!
```

**Issue 3**: Table IDs extracted from compound name prefix (`ocean`, `atmos`) but metadata uses actual table names (`Omon`, `Amon`, `3hr`). Mismatch → no variables loaded.

**After fixing table ID extraction**:
```
Data request has 1974 variables
Rule 'tos_1350' has 1 data_request_variables
Processing 1 rules
Beginning flow run...
```

**Finally processes** (though hits different error in pipeline - unrelated to this issue).

### Key Symptoms

1. **Silent failure**: Rules dropped with no warning (fixed in this PR)
2. **Config ignored**: `CMIP7_DReq_metadata` not used for DataRequest loading
3. **Zero variables**: Multiple bugs cause DataRequest to have 0 variables despite valid metadata
4. **CMIP6 dependency**: Requires `cmip6_table` field that doesn't conceptually exist in pure CMIP7

### Current Workaround

Metadata **must** include `cmip6_table` field with CMIP6 table names (e.g., `Omon`, `3hr`) for every variable, even though CMIP7 doesn't use this concept natively.

## Proposed Solution

### Phase 1: Remove CMIP6 Table Dependency

1. **Index CMIP7 variables by compound name directly**
```python
# Instead of organizing by cmip6_table
for cmip7_name, var_dict in data["Compound Name"].items():
    variable = CMIP7DataRequestVariable.from_dict(var_dict)
    variables[cmip7_name] = variable  # Key by compound name
```

2. **Match compound names directly**
```python
# Compare full compound names, not extracted parts
if rule.compound_name == data_request_variable.variable_id:
    matches.append(rule)
```

3. **Remove table concept from CMIP7 path**
- Keep tables for CMIP6 (backward compatibility)
- For CMIP7: flat dictionary keyed by compound name
- Update `CMIP7DataRequest.__init__()` to accept variables dict directly

### Phase 2: Clean Architecture Separation

1. **Separate CMIP6 and CMIP7 code paths in cmorizer**
```python
if self.cmor_version == "CMIP6":
    self._process_cmip6_rules()
elif self.cmor_version == "CMIP7":
    self._process_cmip7_rules()
```

2. **CMIP7-specific matching logic**
- No table extraction
- Full compound name comparison
- Support wildcards for region/branding (optional enhancement)

3. **Remove `cmip6_table` references from CMIP7 code paths**
- Update global attributes to use CMIP7 native fields
- Don't require backward compatibility fields

## Benefits

1. **Standards compliance**: Uses CMIP7 architecture as designed
2. **Simpler code**: No conversion between CMIP6/CMIP7 concepts
3. **Better error messages**: Clear when CMIP7 compound names don't match
4. **Future-proof**: Independent of CMIP6 evolution
5. **Performance**: No unnecessary table grouping/filtering
6. **Correctness**: Preserves full CMIP7 variable identification (branding, frequency, region)

## Workaround (Current)

Until fixed, users must:
1. Ensure metadata has `cmip6_table` field for every variable
2. Understand that branding/frequency/region are ignored in matching
3. Use full compound names in configs despite partial matching

## Related Files

- `src/pycmor/data_request/collection.py` - DataRequest loading
- `src/pycmor/data_request/table.py` - Table-based organization
- `src/pycmor/data_request/variable.py` - Variable definitions
- `src/pycmor/core/cmorizer.py` - Rule matching logic
- `src/pycmor/std_lib/global_attributes.py` - Output attributes

## Breaking Changes Considerations

- Existing CMIP7 configs should continue working (compound names are already used)
- CMIP6 functionality unaffected (separate code path)
- Internal API changes only (how variables are organized/matched)
- May expose previously silent failures (rules that didn't match due to bugs)

## Testing Requirements

1. CMIP7 metadata **without** `cmip6_table` fields works correctly
2. Compound name matching is exact (includes branding/frequency/region)
3. Multiple variants of same variable (different branding) are distinguished
4. CMIP6 functionality unchanged (regression tests)
5. Output files have correct CMIP7 metadata (no `cmip6_table` references)
