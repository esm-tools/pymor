#!/usr/bin/env python3
"""
Convert CMIP7 variable mapping Excel file to YAML for use in pycmor
"""

import pandas as pd
import yaml
from pathlib import Path
import argparse

def excel_to_yaml(excel_path, yaml_path, filter_status=None):
    """
    Convert Excel variable mapping to YAML format.

    Parameters
    ----------
    excel_path : str or Path
        Path to the Excel file
    yaml_path : str or Path
        Path to output YAML file
    filter_status : str, optional
        Only include variables with this status (e.g., 'completed')
    """
    print("="*80)
    print("CONVERTING EXCEL TO YAML")
    print("="*80)

    # Read Excel file
    print(f"\nReading Excel file: {excel_path}")
    df = pd.read_excel(excel_path, sheet_name='Variable Mapping')
    print(f"Total variables in Excel: {len(df)}")

    # Filter by status if requested
    if filter_status:
        df = df[df['status'] == filter_status]
        print(f"Filtered to status '{filter_status}': {len(df)} variables")

    # Convert to dictionary format
    print("\nConverting to YAML structure...")
    variables = {}

    for _, row in df.iterrows():
        var_id = row['variable_id']

        # Build variable entry
        var_entry = {
            # CMIP7 metadata
            'standard_name': row['standard_name'] if pd.notna(row['standard_name']) else None,
            'long_name': row['long_name'] if pd.notna(row['long_name']) else None,
            'units': row['units'] if pd.notna(row['units']) else None,
            'frequency': row['frequency'] if pd.notna(row['frequency']) else None,
            'modeling_realm': row['modeling_realm'] if pd.notna(row['modeling_realm']) else None,

            # Model mappings
            'model_mappings': {
                'fesom': row['fesom'] if pd.notna(row['fesom']) and row['fesom'] != '' else None,
                'oifs': row['oifs'] if pd.notna(row['oifs']) and row['oifs'] != '' else None,
                'recom': row['recom'] if pd.notna(row['recom']) and row['recom'] != '' else None,
                'lpj_guess': row['lpj_guess'] if pd.notna(row['lpj_guess']) and row['lpj_guess'] != '' else None,
            },

            # Processing information
            'processing': {
                'preprocess': row['preprocess'] if pd.notna(row['preprocess']) and row['preprocess'] != '' else None,
                'formula': row['formula'] if pd.notna(row['formula']) and row['formula'] != '' else None,
                'comment': row['comment'] if pd.notna(row['comment']) and row['comment'] != '' else None,
            },

            # Status
            'status': row['status'] if pd.notna(row['status']) else 'pending',
            'priority': row['priority'] if pd.notna(row['priority']) and row['priority'] != '' else None,
        }

        # Clean up None values in nested dicts
        var_entry['model_mappings'] = {k: v for k, v in var_entry['model_mappings'].items() if v is not None}
        var_entry['processing'] = {k: v for k, v in var_entry['processing'].items() if v is not None}

        # Remove empty nested dicts
        if not var_entry['model_mappings']:
            del var_entry['model_mappings']
        if not var_entry['processing']:
            del var_entry['processing']

        # Remove None values from top level
        var_entry = {k: v for k, v in var_entry.items() if v is not None}

        variables[var_id] = var_entry

    # Write YAML file
    print(f"\nWriting YAML file: {yaml_path}")
    with open(yaml_path, 'w') as f:
        yaml.dump(
            {'cmip7_variables': variables},
            f,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True,
            width=100
        )

    print(f"\n✓ YAML file created successfully")
    print(f"  - Variables included: {len(variables)}")

    # Statistics
    print("\n" + "="*80)
    print("STATISTICS")
    print("="*80)

    # Count variables with model mappings
    with_fesom = sum(1 for v in variables.values() if 'model_mappings' in v and 'fesom' in v['model_mappings'])
    with_oifs = sum(1 for v in variables.values() if 'model_mappings' in v and 'oifs' in v['model_mappings'])
    with_recom = sum(1 for v in variables.values() if 'model_mappings' in v and 'recom' in v['model_mappings'])
    with_lpj = sum(1 for v in variables.values() if 'model_mappings' in v and 'lpj_guess' in v['model_mappings'])

    print(f"Variables with model mappings:")
    print(f"  - FESOM: {with_fesom}")
    print(f"  - OIFS: {with_oifs}")
    print(f"  - REcoM: {with_recom}")
    print(f"  - LPJ-Guess: {with_lpj}")

    # Count by status
    status_counts = {}
    for v in variables.values():
        status = v.get('status', 'pending')
        status_counts[status] = status_counts.get(status, 0) + 1

    print(f"\nVariables by status:")
    for status, count in sorted(status_counts.items()):
        print(f"  - {status}: {count}")

    print("\n" + "="*80)
    print("SAMPLE YAML OUTPUT (first 3 variables)")
    print("="*80)

    # Show sample
    sample_vars = dict(list(variables.items())[:3])
    print(yaml.dump({'cmip7_variables': sample_vars}, default_flow_style=False, sort_keys=True))

    return variables


def main():
    parser = argparse.ArgumentParser(
        description='Convert CMIP7 variable mapping Excel to YAML'
    )
    parser.add_argument(
        '--excel',
        default='cmip7_variable_mapping.xlsx',
        help='Path to Excel file (default: cmip7_variable_mapping.xlsx)'
    )
    parser.add_argument(
        '--yaml',
        default='cmip7_variable_mapping.yaml',
        help='Path to output YAML file (default: cmip7_variable_mapping.yaml)'
    )
    parser.add_argument(
        '--filter-status',
        choices=['pending', 'in_progress', 'completed', 'not_applicable'],
        help='Only include variables with this status'
    )

    args = parser.parse_args()

    # Convert
    excel_to_yaml(args.excel, args.yaml, args.filter_status)

    print("\n" + "="*80)
    print("USAGE IN PYCMOR")
    print("="*80)
    print("""
To use this YAML file in pycmor:

    import yaml

    # Load the variable mapping
    with open('cmip7_variable_mapping.yaml', 'r') as f:
        var_mapping = yaml.safe_load(f)

    # Access variable information
    variables = var_mapping['cmip7_variables']

    # Example: Get FESOM mapping for 'thetao'
    if 'thetao' in variables:
        fesom_var = variables['thetao']['model_mappings']['fesom']
        print(f"CMIP7 'thetao' maps to FESOM '{fesom_var}'")

    # Example: Get all ocean variables mapped to FESOM
    ocean_vars = {
        var_id: var_info
        for var_id, var_info in variables.items()
        if 'ocean' in var_info.get('modeling_realm', '')
        and 'model_mappings' in var_info
        and 'fesom' in var_info['model_mappings']
    }
""")


if __name__ == '__main__':
    main()
