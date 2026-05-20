# CMIP7 Variable Mapping Workflow

This directory contains tools for mapping CMIP7 variables to model-specific variables (FESOM, OIFS, REcoM, LPJ-Guess) for use in the pycmor CMORization pipeline.

## Overview

The workflow provides a user-friendly Excel interface for collaborative variable mapping, which can be converted to YAML for programmatic use in pycmor.

## Files

### Data Files

- **`dreq_v1.2.2.2.json`** - CMIP7 Data Request with experiments and priority levels (required by create script)
- **`dreq_v1.2.2.2_metadata.json`** - CMIP7 variable metadata with compound names, units, standard names (required by create script)
- **`cmip7_variable_mapping.xlsx`** - Excel file with pre-populated CMIP7 variables (1,974 compound names covering 987 unique variables)

### Scripts

- **`create_cmip7_variable_mapping.py`** - Script to generate the Excel file from CMIP7 data request JSON files
- **`excel_to_yaml.py`** - Script to convert filled Excel to YAML format

### Output

- **`cmip7_variable_mapping.yaml`** - Generated YAML file for use in pycmor (created after filling Excel)

## Quick Start

### 1. Create the Excel File (Already Done)

The Excel file has been created with 1,974 compound names covering 987 unique CMIP7 variables:

```bash
conda run -n pycmor-dev python create_cmip7_variable_mapping.py
```

**Note:** The script requires `dreq_v1.2.2.2.json` and `dreq_v1.2.2.2_metadata.json` to be present in the same directory.

**What are compound names?**
Each CMIP7 variable can appear in multiple contexts with different frequencies, regions, or methods. For example:
- `atmos.tas.tavg-h2m-hxy-u.day.GLB` (daily mean)
- `atmos.tas.tavg-h2m-hxy-u.mon.GLB` (monthly mean)
- `atmos.tas.tmax-h2m-hxy-u.day.GLB` (daily maximum)

Each compound name may require different preprocessing, so they are listed separately in the Excel file.

### 2. Fill in the Excel File

Open `cmip7_variable_mapping.xlsx` in Excel or LibreOffice:

**Column Structure:**

| Color | Columns | Description | Action |
|-------|---------|-------------|--------|
| ⬜ Gray | `compound_name`, `table`, `variable_id` | Unique identifiers | **DO NOT EDIT** |
| 🔵 Blue | `standard_name`, `units`, `frequency`, `modeling_realm`, `region`, `method_level_grid`, `dreq_priority` | CMIP7 metadata (pre-populated) | **DO NOT EDIT** |
| 🟢 Green | `fesom`, `oifs`, `recom`, `lpj_guess` | Model-specific variable names | **Fill in as needed** |
| 🟡 Yellow | `preprocess`, `formula`, `comment`, `status`, `user_priority` | Processing information | **Fill in as needed** |

**Example Entries:**

| variable_id | fesom | oifs | recom | lpj_guess | preprocess | status |
|-------------|-------|------|-------|-----------|------------|--------|
| tas | | t2m | | | daily_mean | completed |
| thetao | temp | | | | direct | completed |
| sos | salt | | | | surface_extraction | in_progress |
| so | salt | | | | direct | completed |
| fgco2 | | | co2_flux | | direct | completed |

**Dropdown Values:**
- **status**: `pending`, `in_progress`, `completed`, `not_applicable`
- **user_priority**: `high`, `medium`, `low` (your implementation priority)

**CMIP7 Data Request Priority Levels (read-only):**
- **dreq_priority**: Shows the priority level from CMIP7 experiments
  - **Core** (131 variables): Essential for all CMIP7 experiments
  - **High** (1,038 variables): High priority for most experiments
  - **Medium** (469 variables): Medium priority
  - **Low** (112 variables): Lower priority
  - Some variables have multiple priorities across different experiments (e.g., "High, Medium")

### 3. Convert Excel to YAML

After filling in the Excel file, convert it to YAML:

```bash
# Convert all variables
conda run -n pycmor-dev python excel_to_yaml.py

# Or filter by status (e.g., only completed mappings)
conda run -n pycmor-dev python excel_to_yaml.py --filter-status completed
```

This creates `cmip7_variable_mapping.yaml` for use in pycmor.

## Excel File Details

### Pre-populated CMIP7 Metadata

The following columns are automatically filled from the CMIP7 data request:

- **variable_id**: CMIP7 variable name (e.g., `tas`, `thetao`, `pr`)
- **standard_name**: CF standard name
- **long_name**: Descriptive name
- **units**: Physical units
- **frequency**: Temporal frequency (e.g., `mon`, `day`, `6hr`)
- **modeling_realm**: Realm (e.g., `atmos`, `ocean`, `land`, `aerosol`)

### User Input Columns

#### Model Mappings (Green)
- **fesom**: FESOM ocean model variable name
- **oifs**: OIFS atmosphere model variable name
- **recom**: REcoM biogeochemistry model variable name
- **lpj_guess**: LPJ-Guess land model variable name

#### Processing Information (Yellow)
- **preprocess**: Preprocessing method
  - Examples: `direct`, `avg24h`, `surface_extraction`, `vertical_integration`
- **formula**: Calculation formula for derived variables
  - Example: `var1 + var2`, `sqrt(uas**2 + vas**2)`
- **comment**: Additional notes
- **status**: Mapping status (dropdown)
- **priority**: Priority level (dropdown)

## YAML Output Format

The generated YAML file has the following structure:

```yaml
cmip7_variables:
  tas:
    standard_name: air_temperature
    long_name: Near-Surface Air Temperature
    units: K
    frequency: day, mon
    modeling_realm: atmos
    model_mappings:
      oifs: t2m
    processing:
      preprocess: daily_mean
    status: completed

  thetao:
    standard_name: sea_water_potential_temperature
    long_name: Sea Water Potential Temperature
    units: degC
    frequency: mon
    modeling_realm: ocean
    model_mappings:
      fesom: temp
    processing:
      preprocess: direct
    status: completed
```

## Using the YAML in pycmor

```python
import yaml

# Load the variable mapping
with open('cmip7_variable_mapping.yaml', 'r') as f:
    var_mapping = yaml.safe_load(f)

variables = var_mapping['cmip7_variables']

# Get FESOM mapping for a CMIP7 variable
if 'thetao' in variables:
    fesom_var = variables['thetao']['model_mappings']['fesom']
    preprocess = variables['thetao']['processing']['preprocess']
    print(f"CMIP7 'thetao' -> FESOM '{fesom_var}' (method: {preprocess})")

# Get all ocean variables mapped to FESOM
ocean_fesom_vars = {
    var_id: var_info
    for var_id, var_info in variables.items()
    if 'ocean' in var_info.get('modeling_realm', '')
    and 'model_mappings' in var_info
    and 'fesom' in var_info['model_mappings']
}

print(f"Found {len(ocean_fesom_vars)} ocean variables mapped to FESOM")
```

## Workflow for Collaborative Mapping

1. **Initial Setup** (Done)
   - Excel file created with all CMIP7 variables
   - Shared in pycmor repository

2. **Collaborative Filling**
   - Team members fill in their model-specific mappings
   - Use status column to track progress
   - Use priority column for important variables

3. **Version Control**
   - Commit both Excel and YAML files to repository
   - Track changes via Git
   - Use pull requests for review

4. **Continuous Updates**
   - As mappings are completed, update status
   - Regenerate YAML file
   - Integrate into pycmor workflows

## Data Source

The CMIP7 variable list is extracted from:
- **`dreq_v1.2.2.2_metadata.json`** - CMIP7 Data Request metadata (compound names, units, standard names)
- **`dreq_v1.2.2.2.json`** - Full CMIP7 Data Request (experiments and priority levels)
- Total: **1,974 compound names** covering **987 unique CMIP7 variables**

### Fetching the Data Request Files

The JSON files are included in this repository, but you can also fetch them directly using the CMIP7 Data Request API:

```bash
pip install CMIP7-data-request-api
export_dreq_lists_json -a -m dreq_v1.2.2.2_metadata.json v1.2.2.2 dreq_v1.2.2.2.json
```

This will download the latest version of the CMIP7 Data Request files.

## Preprocessing Method Examples

Common preprocessing methods to use:

- **`direct`**: Direct mapping, no transformation
- **`avg24h`**: 24-hour average
- **`surface_extraction`**: Extract surface level from 3D field
- **`vertical_integration`**: Integrate over vertical levels
- **`time_mean`**: Temporal mean
- **`spatial_mean`**: Spatial mean
- **`regrid`**: Regrid to different grid
- **`unit_conversion`**: Convert units

## Tips

1. **Leave empty if not applicable**: If a CMIP7 variable doesn't apply to your model, leave the model column empty
2. **Use comments**: Add notes about special cases or uncertainties
3. **Set priorities**: Mark high-priority variables for experiments
4. **Track status**: Update status as you progress
5. **Collaborate**: Multiple people can work on different realms simultaneously

## Regenerating the Excel File

If you need to regenerate the Excel file (e.g., after CMIP7 data request update):

```bash
# Backup your current mappings
cp cmip7_variable_mapping.xlsx cmip7_variable_mapping_backup.xlsx

# Regenerate from updated data request
conda run -n pycmor-dev python create_cmip7_variable_mapping.py

# Merge your previous mappings back in (manual step)
```

## Questions or Issues

For questions about:
- **CMIP7 variables**: Check the CMIP7 data request documentation
- **Model variables**: Contact the respective model team
- **pycmor integration**: Open an issue in the pycmor repository

## Related Files

- Conversation history: `cmip7_variable_model_mapping.md`
- CMIP7 data request: `dreq_v1.2.2.2.json`, `dreq_v1.2.2.2_metadata.json`
