#!/usr/bin/env python3
"""
Create Excel file with CMIP7 variables pre-populated from data request.
Uses compound names as unique identifiers to handle duplicate variable names
across different contexts (frequency, region, method, etc.).
"""

import json
import pandas as pd
from pathlib import Path

print("="*80)
print("CREATING CMIP7 VARIABLE MAPPING EXCEL FILE")
print("="*80)

# Load the data request metadata
print("\nLoading CMIP7 Data Request JSON files...")
with open('dreq_v1.2.2.2_metadata.json', 'r') as f:
    dreq_metadata = json.load(f)

compound_names = dreq_metadata.get('Compound Name', {})
print(f"Total compound names found: {len(compound_names)}")

# Create DataFrame with compound names as the primary key
print("\nCreating DataFrame with compound names...")
data = []

for compound_name, details in sorted(compound_names.items()):
    # Parse compound name: realm.variable.method-level-grid-type.frequency.region
    parts = compound_name.split('.')
    
    if len(parts) >= 2:
        realm = parts[0]
        variable = parts[1]
        method_info = parts[2] if len(parts) > 2 else ''
        frequency = parts[3] if len(parts) > 3 else ''
        region = parts[4] if len(parts) > 4 else 'GLB'
        
        # Extract table name (typically realm + frequency)
        # Common CMIP tables: Amon, Omon, Lmon, day, 6hr, etc.
        table = f"{realm[0].upper()}{frequency}" if frequency else realm
        
        row = {
            # Primary identifier
            'compound_name': compound_name,
            'table': table,
            'variable_id': variable,
            
            # CMIP7 metadata (pre-populated)
            'standard_name': details.get('standard_name', '') if isinstance(details, dict) else '',
            'long_name': details.get('title', '') if isinstance(details, dict) else '',
            'units': details.get('units', '') if isinstance(details, dict) else '',
            'frequency': frequency,
            'modeling_realm': realm,
            'region': region,
            'method_level_grid': method_info,
            
            # Model-specific mappings (empty - for user input)
            'fesom': '',
            'oifs': '',
            'recom': '',
            'lpj_guess': '',
            
            # Processing information (empty - for user input)
            'preprocess': '',
            'formula': '',
            'comment': '',
            'status': 'pending',
            'priority': '',
        }
        data.append(row)

df = pd.DataFrame(data)

print(f"Total compound names (rows): {len(df)}")
print(f"Unique variable names: {df['variable_id'].nunique()}")
print(f"Unique tables: {df['table'].nunique()}")

# Create Excel file with formatting
output_file = 'cmip7_variable_mapping.xlsx'
print(f"\nWriting to {output_file}...")

with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    df.to_excel(writer, sheet_name='Variable Mapping', index=False)
    
    # Get the worksheet
    worksheet = writer.sheets['Variable Mapping']
    
    # Set column widths for better readability
    column_widths = {
        'A': 50,  # compound_name
        'B': 15,  # table
        'C': 20,  # variable_id
        'D': 40,  # standard_name
        'E': 50,  # long_name
        'F': 15,  # units
        'G': 12,  # frequency
        'H': 20,  # modeling_realm
        'I': 12,  # region
        'J': 30,  # method_level_grid
        'K': 20,  # fesom
        'L': 20,  # oifs
        'M': 20,  # recom
        'N': 20,  # lpj_guess
        'O': 30,  # preprocess
        'P': 40,  # formula
        'Q': 50,  # comment
        'R': 15,  # status
        'S': 15,  # priority
    }
    
    for col, width in column_widths.items():
        worksheet.column_dimensions[col].width = width
    
    # Freeze the header row and first 3 columns
    worksheet.freeze_panes = 'D2'
    
    # Add data validation for status column
    from openpyxl.worksheet.datavalidation import DataValidation
    
    status_validation = DataValidation(
        type="list",
        formula1='"pending,in_progress,completed,not_applicable"',
        allow_blank=True
    )
    status_validation.error = 'Please select from the dropdown list'
    status_validation.errorTitle = 'Invalid Status'
    worksheet.add_data_validation(status_validation)
    status_validation.add(f'R2:R{len(df)+1}')
    
    # Add data validation for priority column
    priority_validation = DataValidation(
        type="list",
        formula1='"high,medium,low"',
        allow_blank=True
    )
    priority_validation.error = 'Please select from the dropdown list'
    priority_validation.errorTitle = 'Invalid Priority'
    worksheet.add_data_validation(priority_validation)
    priority_validation.add(f'S2:S{len(df)+1}')
    
    # Style the header row
    from openpyxl.styles import Font, PatternFill, Alignment
    
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')
    header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    # Color code different column groups
    # Identifier columns (light gray)
    id_fill = PatternFill(start_color='F0F0F0', end_color='F0F0F0', fill_type='solid')
    for row in range(2, len(df) + 2):
        for col in ['A', 'B', 'C']:
            worksheet[f'{col}{row}'].fill = id_fill
    
    # CMIP7 metadata columns (light blue)
    cmip7_fill = PatternFill(start_color='E7F3FF', end_color='E7F3FF', fill_type='solid')
    for row in range(2, len(df) + 2):
        for col in ['D', 'E', 'F', 'G', 'H', 'I', 'J']:
            worksheet[f'{col}{row}'].fill = cmip7_fill
    
    # Model mapping columns (light green)
    model_fill = PatternFill(start_color='E8F5E9', end_color='E8F5E9', fill_type='solid')
    for row in range(2, len(df) + 2):
        for col in ['K', 'L', 'M', 'N']:
            worksheet[f'{col}{row}'].fill = model_fill
    
    # Processing columns (light yellow)
    process_fill = PatternFill(start_color='FFF9E6', end_color='FFF9E6', fill_type='solid')
    for row in range(2, len(df) + 2):
        for col in ['O', 'P', 'Q', 'R', 'S']:
            worksheet[f'{col}{row}'].fill = process_fill

print(f"\n✓ Excel file created successfully: {output_file}")
print(f"  - Total compound names (rows): {len(df)}")
print(f"  - Unique variable names: {df['variable_id'].nunique()}")
print(f"  - Total columns: {len(df.columns)}")
print(f"  - Identifier columns (gray): 3 (compound_name, table, variable_id)")
print(f"  - CMIP7 metadata columns (blue): 7")
print(f"  - Model mapping columns (green): 4")
print(f"  - Processing columns (yellow): 5")

# Show some statistics
print("\n" + "="*80)
print("STATISTICS")
print("="*80)

print("\nVariables with multiple compound names (top 10):")
var_counts = df['variable_id'].value_counts()
for var, count in var_counts.head(10).items():
    print(f"  {var}: {count} compound names")

print(f"\nFrequency distribution:")
freq_counts = df['frequency'].value_counts()
for freq, count in freq_counts.head(10).items():
    print(f"  {freq}: {count}")

print(f"\nRealm distribution:")
realm_counts = df['modeling_realm'].value_counts()
for realm, count in realm_counts.items():
    print(f"  {realm}: {count}")

print("\n" + "="*80)
print("USAGE INSTRUCTIONS")
print("="*80)
print("""
1. Open cmip7_variable_mapping_v2.xlsx in Excel or LibreOffice
2. Identifier columns (gray) show the unique compound name - DO NOT EDIT
   - compound_name: Full identifier (realm.variable.method.frequency.region)
   - table: CMIP table name
   - variable_id: CMIP7 variable name
3. CMIP7 metadata columns (blue) are pre-populated - DO NOT EDIT
4. Fill in model-specific variable names in green columns:
   - fesom: FESOM variable name
   - oifs: OIFS variable name
   - recom: REcoM variable name
   - lpj_guess: LPJ-Guess variable name
5. Fill in processing information in yellow columns
6. Use filters to work on specific:
   - Variables (e.g., all 'tas' entries)
   - Frequencies (e.g., only 'mon')
   - Realms (e.g., only 'ocean')
   - Tables (e.g., only 'Omon')

Example: The variable 'tas' appears in multiple compound names:
  - atmos.tas.tavg-h2m-hxy-u.day.GLB (daily)
  - atmos.tas.tavg-h2m-hxy-u.mon.GLB (monthly)
  - atmos.tas.tmax-h2m-hxy-u.day.GLB (daily maximum)
  
Each needs to be mapped separately as they may require different preprocessing.
""")

print("="*80)
print("Next step: Use excel_to_yaml.py to convert the filled Excel to YAML")
print("="*80)
