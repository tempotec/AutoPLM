from flask import Blueprint, jsonify, session
from app.models import User, Specification
from app.utils.auth import login_required

api_bp = Blueprint('api', __name__, url_prefix='/api')

STAGE_MAP = {
    0: 'pending',
    1: 'thumbnail',
    2: 'extract_image',
    3: 'extract_text',
    4: 'openai_parse',
    5: 'supplier_link',
    6: 'completed'
}


def get_processing_stage(spec):
    stage_num = spec.processing_stage or 0
    if spec.processing_status == 'error':
        return 'error'
    elif spec.processing_status == 'completed':
        return 'completed'
    return STAGE_MAP.get(stage_num, 'processing')


@api_bp.route('/spec/status/<int:spec_id>', methods=['GET'])
@api_bp.route('/spec_status/<int:spec_id>', methods=['GET'])
@login_required
def get_spec_status(spec_id):
    try:
        spec = Specification.query.get(spec_id)
        if not spec:
            return jsonify({
                'success': False,
                'error': 'Ficha não encontrada'
            }), 404

        user = User.query.get(session['user_id'])
        if not user.is_admin and spec.user_id != user.id:
            return jsonify({'success': False, 'error': 'Acesso negado'}), 403

        return jsonify({
            'success': True,
            'spec_id': spec.id,
            'status': spec.processing_status,
            'processing_stage': get_processing_stage(spec),
            'stage': spec.processing_stage or 0,
            'description': spec.description or 'Processando...',
            'ref_souq': spec.ref_souq or '',
            'has_drawing': bool(spec.technical_drawing_url),
            'error': spec.last_error
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
