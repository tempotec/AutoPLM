"""
Fluxogama API Routes
====================
Blueprint com rotas para preview e envio de payloads ao Fluxogama.
"""
import json
import os
from datetime import datetime
from flask import Blueprint, jsonify, session, request
from app.extensions import csrf, db
from app.models import User, Specification, FichaTecnica, FichaTecnicaItem
from app.utils.auth import login_required
from app.integrations.fluxogama.mapper import build_payload, validate_payload
from app.integrations.fluxogama.client import send_payload

fluxogama_bp = Blueprint('fluxogama', __name__, url_prefix='/api/fluxogama')


def _get_ficha_and_item(ficha_id, item_id):
    """
    Fetch and validate FichaTecnica + FichaTecnicaItem, checking user access.
    Returns (ficha, item, error_response).
    """
    user = User.query.get(session.get('user_id'))
    if not user:
        return None, None, (jsonify({'error': 'Sessão inválida.'}), 401)

    ficha = FichaTecnica.query.get(ficha_id)
    if not ficha:
        return None, None, (jsonify({'error': f'Ficha {ficha_id} não encontrada.'}), 404)

    if not user.is_admin and ficha.user_id != user.id:
        return None, None, (jsonify({'error': 'Acesso negado.'}), 403)

    item = FichaTecnicaItem.query.get(item_id)
    if not item:
        return None, None, (jsonify({'error': f'Item {item_id} não encontrado.'}), 404)

    if item.ficha_id != ficha.id:
        return None, None, (jsonify({'error': 'Item não pertence a esta ficha.'}), 400)

    return ficha, item, None


@fluxogama_bp.route('/payload/ficha/<int:ficha_id>/item/<int:item_id>', methods=['GET'])
@login_required
def preview_payload(ficha_id, item_id):
    """
    GET /api/fluxogama/payload/ficha/<ficha_id>/item/<item_id>
    Preview do JSON que será enviado (sem enviar).
    """
    ficha, item, err = _get_ficha_and_item(ficha_id, item_id)
    if err:
        return err

    payload, errors, warnings = build_payload(ficha, item)
    extra_errors = validate_payload(payload, existing_errors=errors)
    all_errors = errors + extra_errors

    return jsonify({
        'ficha_id': ficha.id,
        'item_id': item.id,
        'payload': payload,
        'errors': all_errors,
        'warnings': warnings,
        'valid': len(all_errors) == 0,
        'fluxogama_status': item.fluxogama_status,
        'fluxogama_sent_at': item.fluxogama_sent_at.isoformat() if item.fluxogama_sent_at else None,
    })


@fluxogama_bp.route('/send/ficha/<int:ficha_id>/item/<int:item_id>', methods=['POST'])
@login_required
@csrf.exempt
def send_to_fluxogama(ficha_id, item_id):
    """
    POST /api/fluxogama/send/ficha/<ficha_id>/item/<item_id>
    Envia payload ao Fluxogama. Use ?dry_run=1 para teste.
    """
    ficha, item, err = _get_ficha_and_item(ficha_id, item_id)
    if err:
        return err

    dry_run = request.args.get('dry_run', '0') in ('1', 'true', 'yes')

    # Dedup check: block resend if already integrated (unless force=1)
    # Fires on dry-run too — "already sent" is important audit info.
    force = request.args.get('force', '0') in ('1', 'true', 'yes')
    if not force and item.fluxogama_status == 'sent':
        return jsonify({
            'ficha_id': ficha.id,
            'item_id': item.id,
            'error': 'Item já foi enviado ao Fluxogama. Use ?force=1 para reenviar.',
            'fluxogama_status': item.fluxogama_status,
            'fluxogama_sent_at': item.fluxogama_sent_at.isoformat() if item.fluxogama_sent_at else None,
        }), 409

    payload, errors, warnings = build_payload(ficha, item)
    extra_errors = validate_payload(payload, existing_errors=errors)
    all_errors = errors + extra_errors

    if all_errors and not dry_run:
        return jsonify({
            'ficha_id': ficha.id,
            'item_id': item.id,
            'payload': payload,
            'errors': all_errors,
            'warnings': warnings,
            'valid': False,
            'sent': False,
        }), 422

    # Model creation support: inject sistema_criar_modelo + subetapa
    allow_create = request.args.get('allow_create', '1') in ('1', 'true', 'yes')
    if allow_create:
        subetapa = request.args.get(
            'subetapa',
            os.environ.get('FLUXOGAMA_SUBETAPA_WSID') or os.environ.get('OAZ_DEFAULT_COLECAO', ''),
        )
        if not subetapa:
            return jsonify({
                'ficha_id': ficha.id,
                'item_id': item.id,
                'error': 'subetapa obrigatória para criação. '
                         'Configure FLUXOGAMA_SUBETAPA_WSID no .env ou passe ?subetapa=<wsid>.',
                'valid': False,
            }), 422
        payload['sistema_criar_modelo'] = 1
        payload['subetapa'] = subetapa

    # Set integration status before sending
    if not dry_run:
        payload['uno.7'] = 'Integrado'

    result = send_payload(payload, dry_run=dry_run)

    # Persist integration result to DB (only on real sends)
    if not dry_run:
        now = datetime.utcnow()
        if result.get('status') == 'success':
            item.fluxogama_status = 'sent'
            item.fluxogama_sent_at = now
            response_snippet = json.dumps(
                result.get('response', ''),
                ensure_ascii=False
            )[:2000]
            item.fluxogama_response = response_snippet
        else:
            item.fluxogama_status = 'error'
            error_info = {
                'error': result.get('error', ''),
                'http_status': result.get('http_status'),
                'response': str(result.get('response', ''))[:500],
            }
            item.fluxogama_response = json.dumps(error_info, ensure_ascii=False)

        db.session.commit()

    return jsonify({
        'ficha_id': ficha.id,
        'item_id': item.id,
        'payload': result.get('payload'),
        'errors': all_errors,
        'warnings': warnings,
        'valid': len(all_errors) == 0,
        'sent': not dry_run and result.get('status') == 'success',
        'dry_run': dry_run,
        'fluxogama_response': result.get('response'),
        'fluxogama_status': result.get('status'),
        'fluxogama_http_status': result.get('http_status'),
        'fluxogama_error': result.get('error'),
        'timestamp': result.get('timestamp'),
    })


MAX_BATCH_SIZE = 100


@fluxogama_bp.route('/send-batch', methods=['POST'])
@login_required
@csrf.exempt
def send_batch():
    """
    POST /api/fluxogama/send-batch
    Envio em lote de itens ao Fluxogama.

    Body JSON: { "ficha_id": int, "item_ids": [int, ...] }
    Query: ?dry_run=1 para teste sem enviar.

    Retorna resultados individuais por item.
    """
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'error': 'Sessão inválida.'}), 401

    data = request.get_json(silent=True) or {}
    ficha_id = data.get('ficha_id')
    item_ids = data.get('item_ids', [])

    if not ficha_id or not item_ids:
        return jsonify({'error': 'ficha_id e item_ids são obrigatórios.'}), 400

    if len(item_ids) > MAX_BATCH_SIZE:
        return jsonify({
            'error': f'Máximo de {MAX_BATCH_SIZE} itens por lote. Recebido: {len(item_ids)}.'
        }), 400

    ficha = FichaTecnica.query.get(ficha_id)
    if not ficha:
        return jsonify({'error': f'Ficha {ficha_id} não encontrada.'}), 404

    if not user.is_admin and ficha.user_id != user.id:
        return jsonify({'error': 'Acesso negado.'}), 403

    dry_run = request.args.get('dry_run', '0') in ('1', 'true', 'yes')
    force = request.args.get('force', '0') in ('1', 'true', 'yes')
    allow_create = request.args.get('allow_create', '1') in ('1', 'true', 'yes')

    # Resolve subetapa once for the whole batch
    subetapa = ''
    if allow_create:
        subetapa = request.args.get(
            'subetapa',
            os.environ.get('FLUXOGAMA_SUBETAPA_WSID') or os.environ.get('OAZ_DEFAULT_COLECAO', ''),
        )
        if not subetapa:
            return jsonify({
                'error': 'subetapa obrigatória para criação. '
                         'Configure FLUXOGAMA_SUBETAPA_WSID no .env ou passe ?subetapa=<wsid>.',
                'valid': False,
            }), 422

    results = []
    success_count = 0
    error_count = 0
    skipped_count = 0

    for item_id in item_ids:
        item = FichaTecnicaItem.query.get(item_id)

        # Item not found or doesn't belong to this ficha
        if not item or item.ficha_id != ficha.id:
            results.append({
                'item_id': item_id,
                'ok': False,
                'message': f'Item {item_id} não encontrado nesta ficha.',
            })
            error_count += 1
            continue

        # Dedup check: skip already-sent items (unless force=1)
        # Fires on dry-run too — "already sent" is audit info.
        if not force and item.fluxogama_status == 'sent':
            results.append({
                'item_id': item_id,
                'ok': True,
                'skipped': True,
                'message': 'Já enviado anteriormente. Use ?force=1 para reenviar.',
                'fluxogama_sent_at': item.fluxogama_sent_at.isoformat() if item.fluxogama_sent_at else None,
            })
            skipped_count += 1
            continue

        # Build and validate payload
        payload, errors, warnings = build_payload(ficha, item)
        extra_errors = validate_payload(payload, existing_errors=errors)
        all_errors = errors + extra_errors

        if all_errors:
            results.append({
                'item_id': item_id,
                'ok': False,
                'message': f'Erros de validação: {"; ".join(all_errors)}',
                'errors': all_errors,
                'warnings': warnings,
            })
            error_count += 1
            continue


        # Model creation support: inject sistema_criar_modelo + subetapa
        if allow_create:
            payload['sistema_criar_modelo'] = 1
            payload['subetapa'] = subetapa

        # Set integration status
        if not dry_run:
            payload['uno.7'] = 'Integrado'

        result = send_payload(payload, dry_run=dry_run)

        # Persist to DB on real sends
        if not dry_run:
            now = datetime.utcnow()
            if result.get('status') == 'success':
                item.fluxogama_status = 'sent'
                item.fluxogama_sent_at = now
                response_snippet = json.dumps(
                    result.get('response', ''),
                    ensure_ascii=False
                )[:2000]
                item.fluxogama_response = response_snippet
                success_count += 1
                results.append({
                    'item_id': item_id,
                    'ok': True,
                    'message': 'Enviado com sucesso.',
                })
            else:
                item.fluxogama_status = 'error'
                error_info = {
                    'error': result.get('error', ''),
                    'http_status': result.get('http_status'),
                    'response': str(result.get('response', ''))[:500],
                }
                item.fluxogama_response = json.dumps(error_info, ensure_ascii=False)
                error_count += 1
                results.append({
                    'item_id': item_id,
                    'ok': False,
                    'message': result.get('error', 'Erro desconhecido.'),
                })
        else:
            success_count += 1
            results.append({
                'item_id': item_id,
                'ok': True,
                'message': 'Dry-run OK.',
            })

    if not dry_run:
        db.session.commit()

    return jsonify({
        'ficha_id': ficha.id,
        'total': len(item_ids),
        'success_count': success_count,
        'error_count': error_count,
        'skipped_count': skipped_count,
        'dry_run': dry_run,
        'results': results,
    })



def _friendly_flux_error(raw_error: str, effective_subetapa: str = '') -> str:
    """Convert raw Fluxogama API errors into actionable user-facing messages."""
    if 'Subetapa não encontrada' in raw_error:
        wsid_note = f" (WSID {effective_subetapa!r})" if effective_subetapa else ''
        return (
            f"Subetapa{wsid_note} não encontrada no Fluxogama para esta coleção. "
            "Edite a ficha e escolha outra subetapa, ou verifique se ela está vinculada à coleção no Fluxogama."
        )
    if 'Coleção não encontrada' in raw_error:
        return "Coleção não encontrada no Fluxogama. Verifique o COLLECTION_MAP e se a coleção está cadastrada."
    if 'Modelo não encontrado' in raw_error:
        return "Modelo não encontrado no Fluxogama. Ative 'Criar modelo' ou verifique a referência da spec."
    return raw_error or 'Erro desconhecido.'


@fluxogama_bp.route('/send-batch-specs', methods=['POST'])
@login_required
@csrf.exempt
def send_batch_specs():
    """
    POST /api/fluxogama/send-batch-specs
    Envio em lote de Specifications (PDFs) ao Fluxogama.

    Body JSON: { "spec_ids": [int, ...] }
    Query: ?dry_run=1 para teste sem enviar.
    """
    print('\n' + '='*60)
    print('[FLUX-BATCH-SPECS] Início do envio em lote')
    print('='*60)

    user = User.query.get(session.get('user_id'))
    if not user:
        print('[FLUX-BATCH-SPECS] ❌ Sessão inválida')
        return jsonify({'error': 'Sessão inválida.'}), 401

    data = request.get_json(silent=True) or {}
    spec_ids = data.get('spec_ids', [])
    print(f'[FLUX-BATCH-SPECS] User: {user.username} | spec_ids: {spec_ids}')
    print(f'[FLUX-BATCH-SPECS] Params: dry_run={request.args.get("dry_run","0")} force={request.args.get("force","0")} allow_create={request.args.get("allow_create","1")} subetapa={request.args.get("subetapa","")} colecao={request.args.get("colecao","")}')

    # Log config
    base_url = os.environ.get('OAZ_BASE_URL') or os.environ.get('FLUXOGAMA_BASE_URL', '')
    chave_preview = (os.environ.get('OAZ_CHAVE') or os.environ.get('FLUXOGAMA_CHAVE', ''))[:20]
    endpoint = os.environ.get('OAZ_MODELO_PUSH_PATH') or os.environ.get('FLUXOGAMA_ENDPOINT_ENVIO', '/remessa/envio')
    print(f'[FLUX-BATCH-SPECS] Config: base_url={base_url} | endpoint={endpoint} | chave={chave_preview}...')

    if not spec_ids:
        print('[FLUX-BATCH-SPECS] ❌ spec_ids vazio')
        return jsonify({'error': 'spec_ids é obrigatório.'}), 400

    if len(spec_ids) > MAX_BATCH_SIZE:
        return jsonify({
            'error': f'Máximo de {MAX_BATCH_SIZE} itens por lote. Recebido: {len(spec_ids)}.'
        }), 400

    dry_run = request.args.get('dry_run', '0') in ('1', 'true', 'yes')
    force = request.args.get('force', '0') in ('1', 'true', 'yes')
    allow_create = request.args.get('allow_create', '1') in ('1', 'true', 'yes')

    # User-provided coleção WSID (overrides COLLECTION_MAP)
    user_colecao = (request.args.get('colecao') or '').strip()

    # Resolve subetapa once for the whole batch (optional for specs)
    subetapa = ''
    if allow_create:
        subetapa = request.args.get(
            'subetapa',
            os.environ.get('FLUXOGAMA_SUBETAPA_WSID') or os.environ.get('OAZ_DEFAULT_COLECAO', ''),
        )

    results = []
    success_count = 0
    error_count = 0

    for i, spec_id in enumerate(spec_ids):
        print(f'\n[FLUX-BATCH-SPECS] ── Spec {i+1}/{len(spec_ids)} (id={spec_id}) ──')
        spec = Specification.query.get(spec_id)
        if not spec:
            print(f'[FLUX-BATCH-SPECS]   ❌ Spec {spec_id} não encontrada no DB')
            results.append({
                'spec_id': spec_id,
                'ok': False,
                'message': f'Specification {spec_id} não encontrada.',
            })
            error_count += 1
            continue

        if not user.is_admin and spec.user_id != user.id:
            results.append({
                'spec_id': spec_id,
                'ok': False,
                'message': 'Acesso negado.',
            })
            error_count += 1
            continue

        # Build payload from Specification fields
        # Maps Specification model fields → Fluxogama uno.X keys
        # aligned with field_map.json and the OAZ /remessa/modelo schema

        # Resolve coleção: user-provided > COLLECTION_MAP fallback
        if user_colecao:
            resolved_collection = user_colecao
            print(f"  [FLUX] Coleção: user_provided='{user_colecao}'")
        else:
            # Fallback: mapeamento de coleções PDF → WSID numérico
            COLLECTION_MAP = {
                'VERÃO 26/27': '61',
                'VERAO 26/27': '61',
                'VERÃO 2026/2027': '61',
                'VERÃO 2027': '61',
                'VERAO 2027': '61',
                'VERÃO 2027 TSM | SOUQ': '61',
                'VERAO 2027 TSM | SOUQ': '61',
                'INVERNO 27': '62',
                'INVERNO 2027': '62',
                'INVERNO 27 - TSM | SOUQ': '62',
            }
            raw_collection = (spec.collection or '').strip()
            resolved_collection = COLLECTION_MAP.get(raw_collection.upper(), raw_collection)
            print(f"  [FLUX] Coleção: '{raw_collection}' → '{resolved_collection}' (via COLLECTION_MAP)")

        payload = {
            'referencia': spec.ref_souq or '',
            'colecao': resolved_collection,
            'ws_id': f'spec_{spec.id}',
            'codigo': f'spec_{spec.id}',

            # uno.1 – Descrição título peça
            'uno.1': spec.description or '',

            # uno.3 – Descrição curta
            'uno.3': spec.description[:80] if spec.description else '',

            # uno.11 – Grupo (DB field)
            'uno.11': spec.main_group or '',

            # uno.12 – Sub Grupo (DB field)
            'uno.12': spec.sub_group or '',

            # uno.23 – Composição
            'uno.23': spec.composition or '',

            # uno.24 – Material Principal (DB field)
            'uno.24': spec.main_fabric or '',

            # uno.9 – Cores
            'uno.9': spec.colors or '',

            # uno.25 – Tam. Piloto
            'uno.25': spec.pilot_size or '',

            # uno.307 – Instruções de cuidados (padrão/tags)
            'uno.307': spec.tags_kit or '',

            # uno.386 – Descrição longa (texto do site)
            'uno.386': spec.specific_details or '',

            # uno.443 – Observações
            'uno.443': spec.finishes or '',
        }

        # Add cors array if colors available
        if spec.colors:
            colors_list = [c.strip() for c in spec.colors.split(',') if c.strip()]
            if colors_list:
                payload['cores'] = [
                    {'cor': c, 'variante': i + 1}
                    for i, c in enumerate(colors_list)
                ]

        # Remove empty values
        payload = {k: v for k, v in payload.items() if v}

        print(f'[FLUX-BATCH-SPECS]   Payload keys: {list(payload.keys())}')
        print(f'[FLUX-BATCH-SPECS]   referencia={payload.get("referencia","")} | colecao={payload.get("colecao","")} | ws_id={payload.get("ws_id","")}')

        if not payload.get('referencia'):
            print(f'[FLUX-BATCH-SPECS]   ❌ Sem referência (ref_souq)')
            results.append({
                'spec_id': spec_id,
                'ok': False,
                'message': 'Sem referência (ref_souq) definida.',
            })
            error_count += 1
            continue

        # Update vs Create logic
        # If spec has fluxogama_model_id → update existing model (just send id + fields)
        # If not → create new model (sistema_criar_modelo + subetapa required)
        fluxogama_id = getattr(spec, 'fluxogama_model_id', None)

        if fluxogama_id:
            # UPDATE MODE: just send the Fluxogama model ID + fields
            payload['id'] = fluxogama_id
            # Remove creation-only fields
            payload.pop('sistema_criar_modelo', None)
            payload.pop('subetapa', None)
            print(f"  [FLUX] UPDATE mode: fluxogama_model_id={fluxogama_id}")
        elif allow_create:
            # CREATE MODE: needs subetapa
            global_sub = (subetapa or '').strip()
            spec_sub = (getattr(spec, 'fluxogama_subetapa', None) or '').strip()
            effective_subetapa = spec_sub or global_sub
            print(f"  [FLUX] CREATE mode: subetapa spec={spec_sub!r} | global={global_sub!r} | effective={effective_subetapa!r}")

            if not effective_subetapa:
                results.append({
                    'spec_id': spec_id,
                    'ok': False,
                    'message': 'Subetapa não definida. Edite a ficha e selecione uma subetapa antes de enviar com allow_create=1.',
                })
                error_count += 1
                continue
            payload['sistema_criar_modelo'] = 1
            payload['subetapa'] = effective_subetapa
        else:
            # No fluxogama_model_id and allow_create=0 → can't send
            results.append({
                'spec_id': spec_id,
                'ok': False,
                'message': 'Sem fluxogama_model_id e allow_create desabilitado. Vincule o ID do Fluxogama ou habilite allow_create.',
            })
            error_count += 1
            continue

        print(f'[FLUX-BATCH-SPECS]   Enviando... (dry_run={dry_run})')
        try:
            result = send_payload(payload, dry_run=dry_run)
            is_ok = result.get('status') in ('success', 'dry_run')

            if is_ok:
                success_count += 1
                print(f'[FLUX-BATCH-SPECS]   ✅ {result.get("status")} | HTTP {result.get("http_status", "—")}')
            else:
                error_count += 1
                print(f'[FLUX-BATCH-SPECS]   ❌ ERRO: {result.get("error", "?")} | HTTP {result.get("http_status", "?")}')
                # Log response body for debugging
                resp_body = result.get('response', '')
                if resp_body:
                    print(f'[FLUX-BATCH-SPECS]   Response body: {str(resp_body)[:500]}')

            results.append({
                'spec_id': spec_id,
                'ok': is_ok,
                'message': 'Enviado com sucesso.' if is_ok else _friendly_flux_error(result.get('error', ''), effective_subetapa),
                'status_code': result.get('http_status'),
            })
        except Exception as exc:
            error_count += 1
            print(f'[FLUX-BATCH-SPECS]   💥 EXCEPTION: {type(exc).__name__}: {exc}')
            import traceback
            traceback.print_exc()
            results.append({
                'spec_id': spec_id,
                'ok': False,
                'message': f'Erro inesperado: {exc}',
            })

    print(f'\n[FLUX-BATCH-SPECS] ══ RESUMO ══')
    print(f'[FLUX-BATCH-SPECS] Total: {len(spec_ids)} | ✅ Sucesso: {success_count} | ❌ Erro: {error_count} | Dry-run: {dry_run}')
    print('='*60 + '\n')

    return jsonify({
        'total': len(spec_ids),
        'success_count': success_count,
        'error_count': error_count,
        'dry_run': dry_run,
        'results': results,
    })
