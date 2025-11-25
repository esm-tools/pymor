#!/usr/bin/env python3
"""
Convert CMIP7 variable mapping Excel file to YAML for use in pycmor.
Uses compound names as unique identifiers.
"""

import argparse

import pandas as pd
import yaml


def excel_to_yaml(excel_path, yaml_path, filter_status=None):
    """
    Convert Excel variable mapping to YAML format.

    Parameters
    ----------
    excel_path : str
        Path to the Excel file
    yaml_path : str
        Path to output YAML file
    filter_status : str, optional
        Only include variables with this status (e.g., 'completed')
    """
    print("=" * 80)
    print("CONVERTING EXCEL TO YAML")
    print("=" * 80)

    # Read Excel file
    print(f"\nReading Excel file: {excel_path}")
    df = pd.read_excel(excel_path, sheet_name="Variable Mapping")
    print(f"Total compound names in Excel: {len(df)}")

    # Filter by status if requested
    if filter_status:
        df = df[df["status"] == filter_status]
        print(f"Filtered to status '{filter_status}': {len(df)} compound names")

    # Convert to dictionary format using compound_name as key
    print("\nConverting to YAML structure...")
    variables = {}

    for _, row in df.iterrows():
        compound_name = row["compound_name"]

        # Build variable entry
        var_entry = {
            # Identifiers
            "table": row["table"] if pd.notna(row["table"]) else None,
            "variable_id": row["variable_id"] if pd.notna(row["variable_id"]) else None,
            # CMIP7 metadata
            "standard_name": (
                row["standard_name"] if pd.notna(row["standard_name"]) else None
            ),
            "long_name": row["long_name"] if pd.notna(row["long_name"]) else None,
            "units": row["units"] if pd.notna(row["units"]) else None,
            "frequency": row["frequency"] if pd.notna(row["frequency"]) else None,
            "modeling_realm": (
                row["modeling_realm"] if pd.notna(row["modeling_realm"]) else None
            ),
            "region": row["region"] if pd.notna(row["region"]) else None,
            "method_level_grid": (
                row["method_level_grid"] if pd.notna(row["method_level_grid"]) else None
            ),
            # Model mappings
            "model_mappings": {
                "fesom": (
                    row["fesom"]
                    if pd.notna(row["fesom"]) and row["fesom"] != ""
                    else None
                ),
                "oifs": (
                    row["oifs"] if pd.notna(row["oifs"]) and row["oifs"] != "" else None
                ),
                "recom": (
                    row["recom"]
                    if pd.notna(row["recom"]) and row["recom"] != ""
                    else None
                ),
                "lpj_guess": (
                    row["lpj_guess"]
                    if pd.notna(row["lpj_guess"]) and row["lpj_guess"] != ""
                    else None
                ),
            },
            # Processing information
            "processing": {
                "preprocess": (
                    row["preprocess"]
                    if pd.notna(row["preprocess"]) and row["preprocess"] != ""
                    else None
                ),
                "formula": (
                    row["formula"]
                    if pd.notna(row["formula"]) and row["formula"] != ""
                    else None
                ),
                "comment": (
                    row["comment"]
                    if pd.notna(row["comment"]) and row["comment"] != ""
                    else None
                ),
            },
            # Status
            "status": row["status"] if pd.notna(row["status"]) else "pending",
            "priority": (
                row["priority"]
                if pd.notna(row["priority"]) and row["priority"] != ""
                else None
            ),
        }

        # Clean up None values in nested dicts
        var_entry["model_mappings"] = {
            k: v for k, v in var_entry["model_mappings"].items() if v is not None
        }
        var_entry["processing"] = {
            k: v for k, v in var_entry["processing"].items() if v is not None
        }

        # Remove empty nested dicts
        if not var_entry["model_mappings"]:
            del var_entry["model_mappings"]
        if not var_entry["processing"]:
            del var_entry["processing"]

        # Remove None values from top level
        var_entry = {k: v for k, v in var_entry.items() if v is not None}

        variables[compound_name] = var_entry

    # Write YAML file
    print(f"\nWriting YAML file: {yaml_path}")
    with open(yaml_path, "w") as f:
        yaml.dump(
            {"cmip7_compound_variables": variables},
            f,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True,
            width=100,
        )

    print("\n✓ YAML file created successfully")
    print(f"  - Compound names included: {len(variables)}")

    # Statistics
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)

    # Count variables with model mappings
    with_fesom = sum(
        1
        for v in variables.values()
        if "model_mappings" in v and "fesom" in v["model_mappings"]
    )
    with_oifs = sum(
        1
        for v in variables.values()
        if "model_mappings" in v and "oifs" in v["model_mappings"]
    )
    with_recom = sum(
        1
        for v in variables.values()
        if "model_mappings" in v and "recom" in v["model_mappings"]
    )
    with_lpj = sum(
        1
        for v in variables.values()
        if "model_mappings" in v and "lpj_guess" in v["model_mappings"]
    )

    print("Compound names with model mappings:")
    print(f"  - FESOM: {with_fesom}")
    print(f"  - OIFS: {with_oifs}")
    print(f"  - REcoM: {with_recom}")
    print(f"  - LPJ-Guess: {with_lpj}")

    # Count by status
    status_counts = {}
    for v in variables.values():
        status = v.get("status", "pending")
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\nCompound names by status:")
    for status, count in sorted(status_counts.items()):
        print(f"  - {status}: {count}")

    # Count unique variable_ids
    unique_vars = set(
        v.get("variable_id") for v in variables.values() if v.get("variable_id")
    )
    print(f"\nUnique variable_ids: {len(unique_vars)}")

    print("\n" + "=" * 80)
    print("SAMPLE YAML OUTPUT (first 3 compound names)")
    print("=" * 80)

    # Show sample
    sample_vars = dict(list(variables.items())[:3])
    print(
        yaml.dump(
            {"cmip7_compound_variables": sample_vars},
            default_flow_style=False,
            sort_keys=True,
        )
    )

    return variables


def main():
    parser = argparse.ArgumentParser(
        description="Convert CMIP7 variable mapping Excel to YAML"
    )
    parser.add_argument(
        "--excel",
        default="cmip7_variable_mapping.xlsx",
        help="Path to Excel file (default: cmip7_variable_mapping.xlsx)",
    )
    parser.add_argument(
        "--yaml",
        default="cmip7_variable_mapping.yaml",
        help="Path to output YAML file (default: cmip7_variable_mapping.yaml)",
    )
    parser.add_argument(
        "--filter-status",
        choices=["pending", "in_progress", "completed", "not_applicable"],
        help="Only include variables with this status",
    )

    args = parser.parse_args()

    # Convert
    excel_to_yaml(args.excel, args.yaml, args.filter_status)

    print("\n" + "=" * 80)
    print("USAGE IN PYCMOR")
    print("=" * 80)
    print(
        """
To use this YAML file in pycmor:

    import yaml

    # Load the variable mapping
    with open('cmip7_variable_mapping.yaml', 'r') as f:
        var_mapping = yaml.safe_load(f)

    # Access compound variable information
    compound_vars = var_mapping['cmip7_compound_variables']

    # Example: Get OIFS mapping for daily mean tas
    compound_name = 'atmos.tas.tavg-h2m-hxy-u.day.GLB'
    if compound_name in compound_vars:
        oifs_var = compound_vars[compound_name]['model_mappings']['oifs']
        preprocess = compound_vars[compound_name]['processing']['preprocess']
        print(f"{compound_name} -> OIFS '{oifs_var}' (method: {preprocess})")

    # Example: Get all monthly ocean variables mapped to FESOM
    ocean_fesom_vars = {
        comp_name: var_info
        for comp_name, var_info in compound_vars.items()
        if var_info.get('frequency') == 'mon'
        and 'ocean' in var_info.get('modeling_realm', '')
        and 'model_mappings' in var_info
        and 'fesom' in var_info['model_mappings']
    }

    # Example: Get all variants of a specific variable
    tas_variants = {
        comp_name: var_info
        for comp_name, var_info in compound_vars.items()
        if var_info.get('variable_id') == 'tas'
    }
    print(f"Found {len(tas_variants)} variants of 'tas'")
"""
    )


if __name__ == "__main__":
    main()
