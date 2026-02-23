"""Debug: parse BANCO - LINHA.xlsx and show what the parser sees."""
import json
from app.utils.excel_parser import parse_excel

with open(r'C:\Users\USER\Downloads\BANCO - LINHA.xlsx', 'rb') as f:
    file_bytes = f.read()

result = parse_excel(file_bytes)

print("=== PARSE RESULT ===")
print(f"Errors:   {result['errors']}")
print(f"Warnings: {result['warnings']}")
print(f"Items:    {len(result['items'])}")
print(f"Invalid:  {len(result['invalid_rows'])}")
print(f"Columns:  {len(result['columns'])}")

print("\n=== COLUMNS DETECTED ===")
for c in result['columns']:
    print(f"  [{c['index']}] source='{c['sourceColumnName']}' -> mapped='{c['name']}'")

print("\n=== HEADER DATA ===")
for k, v in result.get('header', {}).items():
    print(f"  {k}: {v}")

if result['invalid_rows']:
    print(f"\n=== INVALID ROWS (first 5) ===")
    for inv in result['invalid_rows'][:5]:
        print(f"  Row {inv['row']}: errors={inv['errors']}")
        raw = inv.get('rawRow', {})
        for k, v in raw.items():
            if v:
                print(f"    {k}: {v}")

if result['items']:
    print(f"\n=== FIRST 3 ITEMS ===")
    for item in result['items'][:3]:
        print(f"  ---")
        for k, v in item.items():
            if v and k != 'raw_row':
                print(f"    {k}: {v}")
else:
    print("\n*** NO ITEMS PARSED ***")
    # Show first few data rows to understand the file structure
    import pandas as pd
    import io
    stream = io.BytesIO(file_bytes)
    xl = pd.ExcelFile(stream, engine='openpyxl')
    print(f"\n=== SHEET NAMES: {xl.sheet_names} ===")
    sheet = 'SOUQ' if 'SOUQ' in xl.sheet_names else xl.sheet_names[0]
    df = xl.parse(sheet_name=sheet, header=None)
    print(f"Total rows: {len(df)}, columns: {len(df.columns)}")
    print(f"\n=== FIRST 15 ROWS (raw) ===")
    for i in range(min(15, len(df))):
        row = df.iloc[i].tolist()
        non_empty = [(j, v) for j, v in enumerate(row) if pd.notna(v)]
        if non_empty:
            vals = [f"[{j}]={v}" for j, v in non_empty[:8]]
            print(f"  Row {i}: {', '.join(vals)}")
