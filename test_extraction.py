# -*- coding: utf-8 -*-
"""Quick test to verify regex extraction works on the CAMISETA CHIC PDF text."""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from app.utils.ai import (
    _normalize_pdf_text, _extract_label_value, _guess_ref_souq,
    _guess_target_price, _guess_dates_from_text,
    _parse_br_date, _is_blank, _extract_labeled_fields,
    _parse_br_date as parse_date
)

# Texto real extraido do PDF (copiado do log)
PDF_TEXT = """REF SOUQ:
CORNER: TEES
TARGET PRICE:FORNECEDOR:
DESCRICAO: DATA ENTREGA PILOTO:
ESTILISTA: THAIS/ BRUNA MES LOJA:  COLECAO: VERAO 26/27  S27TH026
CAMISETA CHIC
OBSERVACOES/ AVIAMENTOS                                                MATERIA-PRIMA E COMPOSICAO CORES
DESENHO TECNICO
TAM. DA PILOTO: PP FICHA TECNICA SOUQ
MES ENTREGA CD: PA            MO
DATA ENTREGA FICHA- TECNICA:
KIT ETIQUETAS + TAG + PENDURADOR CABIDEMOSTRUARIO PARA:
 MEIA MALHA FIO
R$ 35,00 TOMAZELLI 04/02/26 12/01/26 01/04/26
OFF WHITE
Decote careca em ribana 2,0 cm costura rebativa e cobre gola barra de 3,0 cm com
estampa a 6 cm do decote
sem cava
ARTE: SILK BASE D'AGUA SEM BASE BRANCA PARA FICAR BEM LEVE
modelagem: BLUSA MAHARA -  S26TH070"""

print("=" * 70)
print("TESTE DE EXTRACAO - CAMISETA CHIC S27TH026")
print("=" * 70)

norm = _normalize_pdf_text(PDF_TEXT)
print(f"\nLinhas normalizadas: {len(norm['lines'])}")
for i, ln in enumerate(norm['lines']):
    print(f"  [{i:2d}] {ln}")

# Extracao robusta por label
print(f"\n{'='*70}")
print("EXTRACAO ROBUSTA (multi-estrategia):")
ROBUST_LABELS = {
    "ref_souq": ["REF SOUQ", "REF. SOUQ", "REF SOUQ (SOUQ)"],
    "target_price": ["TARGET PRICE", "PRECO ALVO", "TARGET PRICE (R$)"],
    "pilot_delivery_date": ["DATA ENTREGA PILOTO"],
    "tech_sheet_delivery_date": ["DATA ENTREGA FICHA-TECNICA", "DATA ENTREGA FICHA TECNICA"],
    "showcase_for": ["MOSTRUARIO PARA", "MOSTRUARIO PARA"],
    "collection": ["COLECAO", "COLECAO"],
    "corner": ["CORNER"],
    "supplier": ["FORNECEDOR"],
}
robust = {}
for field, lbs in ROBUST_LABELS.items():
    val = _extract_label_value(norm, lbs)
    if val:
        robust[field] = val
        print(f"  LABEL OK {field}: {val}")
    else:
        print(f"  LABEL -- {field}: (nao encontrado por label)")

# Heuristicas
print(f"\n{'='*70}")
print("HEURISTICAS:")

if not robust.get("ref_souq"):
    guessed = _guess_ref_souq(norm)
    if guessed:
        robust["ref_souq"] = guessed
        print(f"  REF SOUQ por heuristica: {guessed}")
    else:
        print(f"  REF SOUQ: FAIL - nenhum padrao encontrado")
else:
    print(f"  REF SOUQ: ja extraida por label: {robust['ref_souq']}")

if not robust.get("target_price"):
    guessed_price = _guess_target_price(norm)
    if guessed_price:
        robust["target_price"] = guessed_price
        print(f"  TARGET PRICE por heuristica: {guessed_price}")
    else:
        print(f"  TARGET PRICE: FAIL - nenhum R$ encontrado")
else:
    print(f"  TARGET PRICE: ja extraido por label: {robust['target_price']}")

import re as _re

def _looks_like_date(val):
    return bool(val and _re.search(r'\d{2}/\d{2}/\d{2,4}', val))

guessed_dates = _guess_dates_from_text(norm)
if not _looks_like_date(robust.get("pilot_delivery_date")) and guessed_dates.get("pilot_delivery_date"):
    robust["pilot_delivery_date"] = guessed_dates["pilot_delivery_date"]
    print(f"  PILOT DATE por heuristica: {guessed_dates['pilot_delivery_date']}")
else:
    print(f"  PILOT DATE: ja extraido: {robust.get('pilot_delivery_date')}")

if not _looks_like_date(robust.get("tech_sheet_delivery_date")) and guessed_dates.get("tech_sheet_delivery_date"):
    robust["tech_sheet_delivery_date"] = guessed_dates["tech_sheet_delivery_date"]
    print(f"  TECH DATE por heuristica: {guessed_dates['tech_sheet_delivery_date']}")
else:
    print(f"  TECH DATE: ja extraido: {robust.get('tech_sheet_delivery_date')}")

# Normalizar datas
for dk in ("pilot_delivery_date", "tech_sheet_delivery_date"):
    raw = robust.get(dk)
    parsed = _parse_br_date(raw) if raw else None
    if parsed:
        robust[dk] = parsed

# Resultado final
print(f"\n{'='*70}")
print("RESULTADO FINAL:")
print(f"{'='*70}")

checks = {
    "ref_souq": ("S27TH026", robust.get("ref_souq")),
    "target_price": ("R$", robust.get("target_price")),
    "pilot_delivery_date": ("2026-01-12", robust.get("pilot_delivery_date")),
    "tech_sheet_delivery_date": ("2026-02-04", robust.get("tech_sheet_delivery_date")),
}

all_ok = True
for field, (expected, actual) in checks.items():
    ok = expected in (actual or "")
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {field}: esperado contem '{expected}', obtido='{actual}'")
    if not ok:
        all_ok = False

print(f"\n{'='*70}")
if all_ok:
    print(">>> TODOS OS TESTES PASSARAM! <<<")
else:
    print(">>> ALGUNS TESTES FALHARAM <<<")
print(f"{'='*70}")
