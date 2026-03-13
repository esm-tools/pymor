# Plan for CMIP7 CMORization of SST for AWI-ESM3-VEG-LR (piControl)

This document provides a plan for the builder AI to configure and run `pycmor` to cmorize a single variable (`sst`) for one year (`1350`) from FESOM output in the AWI-ESM3-VEG-LR piControl experiment into the **CMIP7** standard.

## 1. Goal Overview
- **Model:** AWI-ESM3-VEG-LR
- **Experiment:** piControl
- **Input Data:** `/work/bb1469/a270092/runtime/awiesm3-v3.4.1/human_tuning/outdata/fesom/sst.fesom.1350.nc`
- **Model Variable:** `sst`
- **CMOR Variable:** `tos` (Sea Surface Temperature, Table: `Omon`)
- **Target Standard:** CMIP7

## 2. CMIP7 Specific Requirements in `pycmor`
Unlike CMIP6, the CMIP7 data request in `pycmor` is driven by a unified `all_var_info.json` file.
- The `general` configuration block must explicitly set `cmor_version: "CMIP7"`.
- `CMIP_Tables_Dir` must point to a directory containing the `all_var_info.json` file. You should use `/work/ab0246/a270092/software/pycmor/src/pycmor/data/cmip7` (which is already populated in the codebase).
- `CV_Dir` (Controlled Vocabularies) configuration is still required. Since the local `cmip6-cmor-tables` submodule is empty, use the shared cluster path found in existing examples: `/work/ab0246/a270077/SciComp/Projects/pycmor/cmip6-cmor-tables/CMIP6_CVs`.

## 3. Configuration YAML Structure
The builder AI should generate a `pycmor` configuration file (e.g., `cmorize_sst.yaml`) with the following structure:

```yaml
general:
  name: "AWI-ESM3-VEG-LR PI Control SST"
  description: "CMIP7 CMORization of SST for AWI-ESM3-VEG-LR piControl experiment"
  maintainer: "Your Name"
  email: "your.email@awi.de"
  cmor_version: "CMIP7"
  mip: "CMIP"
  # Shared path for CVs
  CV_Dir: "/work/ab0246/a270077/SciComp/Projects/pycmor/cmip6-cmor-tables/CMIP6_CVs"
  # Path to the directory containing all_var_info.json for CMIP7
  CMIP_Tables_Dir: "/work/ab0246/a270092/software/pycmor/src/pycmor/data/cmip7"

rules:
  - name: sst_tos_rule
    description: "Cmorize FESOM SST to CMIP7 tos"
    cmor_variable: tos
    model_variable: sst
    # Specify the target directory for the CMORized output
    output_directory: ./cmorized_output
    variant_label: r1i1p1f1
    experiment_id: piControl
    source_id: AWI-ESM3-VEG-LR
    model_component: ocean
    grid_label: gn
    inputs:
      - path: /work/bb1469/a270092/runtime/awiesm3-v3.4.1/human_tuning/outdata/fesom
        pattern: sst\.fesom\.1350\.nc
```

## 4. Execution Steps for the Builder AI
1. **Create the configuration file:** Write the YAML configuration above to a file (e.g., `cmorize_sst.yaml`).
2. **Setup pycmor environment:** Ensure `pycmor` is installed in the current python environment or install it using `pip install -e .` from the repository root (`/work/ab0246/a270092/software/pycmor`).
3. **Execute pycmor:** Run the configuration through the pycmor CLI.
   ```bash
   pycmor process cmorize_sst.yaml
   ```
4. **Verify Output:** Check the `output_directory` to confirm the file has been created following the CMIP7 directory structure and naming conventions (e.g., `CMIP7/.../tos_...nc`), and verify the internal NetCDF metadata conforms to CMIP7 standards.
