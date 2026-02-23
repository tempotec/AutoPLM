import os, json, sys
os.environ['APP_ENV'] = 'development'
from app import create_app
app = create_app()

out = open('_inspect_output.txt', 'w', encoding='utf-8')

with app.app_context():
    from app.models import FichaTecnica, FichaTecnicaItem
    f = FichaTecnica.query.get(7)

    out.write("=== COLUMNS META ===\n")
    if f.columns_meta:
        cols = json.loads(f.columns_meta)
        for c in cols:
            idx = c.get("index", "?")
            src = c.get("sourceColumnName", "")
            nm = c.get("name", "")
            out.write(f"  idx={idx}  src=[{src}]  name=[{nm}]\n")

    out.write("\n=== FIRST ITEM RAW_ROW KEYS ===\n")
    item = FichaTecnicaItem.query.filter_by(ficha_id=7).first()
    if item and item.raw_row:
        rr = json.loads(item.raw_row)
        for k, v in rr.items():
            val_preview = str(v)[:50] if v else "(vazio)"
            out.write(f"  [{k}] = {val_preview}\n")

    out.write("\n=== HEADER_RAW ===\n")
    if f.header_raw:
        hr = json.loads(f.header_raw)
        rows = hr if isinstance(hr, list) else [hr]
        for row_data in rows[:15]:
            vals = row_data.get("values", []) if isinstance(row_data, dict) else []
            non_empty = [(i, str(v)[:40]) for i, v in enumerate(vals) if v]
            if non_empty:
                row_num = row_data.get("row", "?")
                out.write(f"  row {row_num}: {non_empty}\n")

out.close()
print("Done - check _inspect_output.txt")
