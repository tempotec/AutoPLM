from flask import Blueprint, jsonify, session
from app.models import User, Specification
from app.utils.auth import login_required

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/spec/status/<int:spec_id>', methods=['GET'])
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
            'description': spec.description or 'Processando...',
            'ref_souq': spec.ref_souq or '',
            'has_drawing': bool(spec.technical_drawing_url)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
