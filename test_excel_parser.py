"""
Testes automatizados para o excel_parser.py
Cobre os 4+ cenários:
  1) Header e mapeamento (variações de nome, duplicatas, Unnamed)
  2) Normalização de valores "lixo"
  3) Validação por linha (severity=error, bloqueio)
  4) Comportamento de colunas (detectadas/missing/unmapped)
  5) Deduplicação de item_no
  6) Normalização de qty (float→int, fracionário)
"""
import io
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from app.utils.excel_parser import (
    parse_excel, normalize_column_name, parse_number, clean_string,
    _find_header_row, COLUMN_MAP
)


def _make_xlsx(headers, rows, sheet_name='Sheet1', header_prefix_rows=None):
    """Create in-memory XLSX."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        all_rows = []
        if header_prefix_rows:
            all_rows.extend(header_prefix_rows)
        all_rows.append(headers)
        all_rows.extend(rows)
        df = pd.DataFrame(all_rows)
        df.to_excel(writer, sheet_name=sheet_name, header=False, index=False)
    return output.getvalue()


passed = 0
failed = 0

def ok(name):
    global passed
    passed += 1
    print(f'  ✅ {name}')


def fail(name, detail=''):
    global failed
    failed += 1
    print(f'  ❌ {name}: {detail}')


# ═══════════════════════════════════════════════════════════════
# 1) HEADER & MAPEAMENTO
# ═══════════════════════════════════════════════════════════════
def test_header_variations():
    print('\n═══ 1) Header e Mapeamento ═══')

    assert normalize_column_name('OAZ QTY ') == 'oaz_qty'; ok('OAZ QTY com espaço → oaz_qty')
    assert normalize_column_name('OAZ\nQTY') == 'oaz_qty';  ok('OAZ\\nQTY → oaz_qty')
    assert normalize_column_name('OAZ_QTY') == 'oaz_qty';   ok('OAZ_QTY → oaz_qty')

    n = normalize_column_name('ITEM NO.(REF. SUPPLIER)')
    assert n in COLUMN_MAP; ok(f'ITEM NO.(REF. SUPPLIER) → {n} → mapped')

    # Duplicate MOQ
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'MOQ', 'OAZ QTY'],
        [['ABC-001', 10, 20, 30]],
    ))
    cols = [c['name'] for c in result['columns']]
    assert 'moq' in cols and 'moq_2' in cols; ok(f'Duplicata MOQ → {cols}')

    # Unnamed columns
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', None, 'MOQ', None, 'OAZ QTY'],
        [['XYZ-002', 'extra', 5, 'more', 10]],
    ))
    assert len(result.get('unmapped_columns', [])) >= 2; ok(f'{len(result["unmapped_columns"])} unmapped')

    # Header in row 3
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'COLOR', 'MOQ', 'OAZ QTY', 'UNIT PRICE'],
        [['REF-001', 'BLUE', 10, 20, 5.5]],
        header_prefix_rows=[
            ['PROFORMA INVOICE', 'PI-2025-001', None, None, None],
            ['BUYER:', 'OAZ COMERCIAL', None, None, None],
        ],
    ))
    assert len(result['items']) == 1 and not result['errors']; ok('Header na linha 3 ok')


# ═══════════════════════════════════════════════════════════════
# 2) NORMALIZAÇÃO DE VALORES
# ═══════════════════════════════════════════════════════════════
def test_value_normalization():
    print('\n═══ 2) Normalização de Valores ═══')

    for val in ['N/A', '—', '-', 'null', 'none', '   ']:
        assert parse_number(val) is None; ok(f'parse_number("{val}") → None')

    assert parse_number('10') == 10.0;       ok('parse_number("10") → 10.0')
    assert parse_number('10,0') == 10.0;     ok('parse_number("10,0") → 10.0')
    assert parse_number('1.000,50') == 1000.5; ok('parse_number("1.000,50") → 1000.5')

    for val in ['N/A', '—', '  ']:
        assert clean_string(val) is None; ok(f'clean_string("{val}") → None')
    assert clean_string('ABC') == 'ABC'; ok('clean_string("ABC") → "ABC"')

    # Full pipeline: N/A → default 0
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['REF-001', 'N/A', '—']],
    ))
    assert len(result['items']) == 1
    assert result['items'][0]['moq'] == 0
    assert result['items'][0]['oaz_qty'] == 0
    ok('MOQ="N/A", OAZ="—" → default 0, item válido')


# ═══════════════════════════════════════════════════════════════
# 3) VALIDAÇÃO POR LINHA (severity=error)
# ═══════════════════════════════════════════════════════════════
def test_row_validation():
    print('\n═══ 3) Validação por Linha ═══')

    # item_no empty with other values → invalid (error severity)
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['', 10, 20], ['REF-002', 5, 10]],
    ))
    assert len(result['items']) == 1 and len(result['invalid_rows']) == 1
    # Check message is severity=error (not warning)
    inv_msgs = [m for m in result['messages'] if m['severity'] == 'error' and 'item_no' in m['text']]
    assert len(inv_msgs) == 1; ok(f'item_no vazio → severity=error: "{inv_msgs[0]["text"][:50]}..."')

    # item_no filled, rest empty → valid (defaults)
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['REF-003', None, None]],
    ))
    assert len(result['items']) == 1
    assert result['items'][0]['moq'] == 0 and result['items'][0]['oaz_qty'] == 0
    ok('item_no + resto vazio → válida (defaults 0)')

    # Empty row → skipped
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [[None, None, None], ['REF-004', 1, 2]],
    ))
    assert len(result['items']) == 1 and len(result['invalid_rows']) == 0
    ok('Linha vazia → ignorada')

    # Overflow: 30 invalid rows → capped at 20 samples
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['', i, i] for i in range(30)] + [['REF-VALID', 1, 1]],
    ))
    assert len(result['items']) == 1
    assert len(result['invalid_rows']) <= 20
    cs = result.get('counts_summary', {})
    assert cs['invalid'] == 30
    ok(f'30 inválidas → {len(result["invalid_rows"])} amostras, count_summary.invalid={cs["invalid"]}')

    # ALL rows invalid → import blocked (error)
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['', 10, 20], ['', 5, 10]],
    ))
    assert len(result['items']) == 0
    block_msgs = [m for m in result['messages'] if m['severity'] == 'error' and 'impossível' in m['text'].lower()]
    assert len(block_msgs) == 1; ok(f'0 válidas → bloqueio: "{block_msgs[0]["text"]}"')


# ═══════════════════════════════════════════════════════════════
# 4) COLUNAS DETECTADAS
# ═══════════════════════════════════════════════════════════════
def test_column_detection():
    print('\n═══ 4) Colunas Detectadas ═══')

    # MOQ/OAZ_QTY missing → warning (not error)
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'COLOR', 'MATERIAL'],
        [['REF-001', 'RED', 'COTTON']],
    ))
    assert not result['errors']
    assert 'moq' in result['missing_columns']
    warn_msgs = [m for m in result['messages'] if m['severity'] == 'warning']
    assert len(warn_msgs) >= 1; ok('MOQ/OAZ ausentes → warning, import OK')

    # item_no missing entirely → ERROR
    result = parse_excel(_make_xlsx(
        ['COLOR', 'MOQ', 'OAZ QTY'],
        [['RED', 10, 20]],
    ))
    assert result['errors']
    assert len(result['items']) == 0
    err_msgs = [m for m in result['messages'] if m['severity'] == 'error']
    assert len(err_msgs) >= 1; ok(f'item_no ausente → ERROR, bloqueado')

    # All 3 present → no messages
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['REF-OK', 10, 20]],
    ))
    assert not result['errors'] and not result['missing_columns']
    ok('Todas colunas presentes → sem messages')


# ═══════════════════════════════════════════════════════════════
# 5) DEDUPLICAÇÃO
# ═══════════════════════════════════════════════════════════════
def test_deduplication():
    print('\n═══ 5) Deduplicação ═══')

    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [
            ['REF-001', 10, 20],
            ['REF-002', 5, 10],
            ['REF-001', 15, 25],  # duplicata
            ['REF-003', 1, 1],
            ['REF-002', 3, 6],   # duplicata
        ],
    ))
    assert len(result['items']) == 5  # all kept (not removed)
    dups = result.get('duplicates', {})
    assert 'REF-001' in dups and dups['REF-001'] == 2
    assert 'REF-002' in dups and dups['REF-002'] == 2
    assert 'REF-003' not in dups
    cs = result.get('counts_summary', {})
    assert cs['duplicated_refs'] == 2
    dup_msgs = [m for m in result['messages'] if 'duplicado' in m['text']]
    assert len(dup_msgs) == 1; ok(f'2 refs duplicados detectados: "{dup_msgs[0]["text"][:60]}..."')

    # No duplicates
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['A', 1, 1], ['B', 2, 2]],
    ))
    assert not result.get('duplicates', {})
    ok('Sem duplicatas → nenhum warning')


# ═══════════════════════════════════════════════════════════════
# 6) NORMALIZAÇÃO DE QTY
# ═══════════════════════════════════════════════════════════════
def test_qty_normalization():
    print('\n═══ 6) Normalização de Qty ═══')

    # Whole float → int
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['REF-001', 10.0, 20.0]],
    ))
    item = result['items'][0]
    assert item['moq'] == 10 and isinstance(item['moq'], int)
    assert item['oaz_qty'] == 20 and isinstance(item['oaz_qty'], int)
    ok('10.0 → 10 (int), 20.0 → 20 (int)')

    # Fractional → ceil'd + warning
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['REF-002', 10.5, 20.7]],
    ))
    item = result['items'][0]
    assert item['moq'] == 11  # math.ceil(10.5) = 11
    assert item['oaz_qty'] == 21  # math.ceil(20.7) = 21
    assert isinstance(item['moq'], int)
    assert isinstance(item['oaz_qty'], int)
    frac_msgs = [m for m in result['messages'] if 'fracionário' in m['text']]
    assert len(frac_msgs) == 1
    cs = result.get('counts_summary', {})
    assert cs['fractional_qty'] >= 1
    ok(f'10.5/20.7 → arredondados + warning: "{frac_msgs[0]["text"][:60]}..."')

    # Default 0 for missing (already tested, but verify type)
    result = parse_excel(_make_xlsx(
        ['ITEM NO.(REF. SUPPLIER)', 'MOQ', 'OAZ QTY'],
        [['REF-003', None, None]],
    ))
    item = result['items'][0]
    assert item['moq'] == 0 and item['oaz_qty'] == 0
    ok('None → default 0')


# ════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('╔══════════════════════════════════════════════╗')
    print('║  Testes do Excel Parser v2 - Completo        ║')
    print('╚══════════════════════════════════════════════╝')

    try:
        test_header_variations()
        test_value_normalization()
        test_row_validation()
        test_column_detection()
        test_deduplication()
        test_qty_normalization()
        print(f'\n🎉 {passed} testes passaram, {failed} falharam')
    except AssertionError as e:
        print(f'\n💥 FALHA: {e}')
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f'\n💥 ERRO: {e}')
        import traceback
        traceback.print_exc()
