import json
import math
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify
from app.extensions import db
from app.models import User, Supplier, Specification
from app.utils.auth import login_required
from app.utils.logging import log_activity, rpa_info, rpa_error

suppliers_bp = Blueprint('suppliers', __name__)


@suppliers_bp.route('/suppliers')
@login_required
def index():
    class SimplePagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = int(math.ceil(total / float(per_page))) if total else 0

        @property
        def has_prev(self):
            return self.page > 1

        @property
        def has_next(self):
            return self.page < self.pages

        @property
        def prev_num(self):
            return self.page - 1

        @property
        def next_num(self):
            return self.page + 1

        def iter_pages(self, left_edge=1, right_edge=1, left_current=1, right_current=2):
            last = 0
            for num in range(1, self.pages + 1):
                if (
                    num <= left_edge
                    or (self.page - left_current - 1 < num < self.page + right_current)
                    or num > self.pages - right_edge
                ):
                    if last + 1 != num:
                        yield None
                    yield num
                    last = num

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    search_query = request.args.get('search', '')
    material_filter = request.args.get('material', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 5

    if user.is_admin:
        query = Supplier.query
    else:
        query = Supplier.query.filter_by(user_id=user.id)

    if search_query:
        query = query.filter(Supplier.name.ilike(f'%{search_query}%'))

    suppliers_list = query.order_by(Supplier.created_at.desc()).all()

    materials_options = {}
    for supplier in suppliers_list:
        if not supplier.materials_json:
            continue
        try:
            materials = json.loads(supplier.materials_json)
        except json.JSONDecodeError:
            continue
        for material in materials:
            name = material.get('name', '').strip()
            if not name:
                continue
            key = name.lower()
            if key not in materials_options:
                materials_options[key] = name

    if material_filter:
        material_filter_lower = material_filter.lower()
        filtered_suppliers = []
        for supplier in suppliers_list:
            if not supplier.materials_json:
                continue
            try:
                materials = json.loads(supplier.materials_json)
            except json.JSONDecodeError:
                continue
            if any(material_filter_lower in (m.get('name', '').lower()) for m in materials):
                filtered_suppliers.append(supplier)
        suppliers_list = filtered_suppliers

    total = len(suppliers_list)
    start = (page - 1) * per_page
    end = start + per_page
    suppliers_paginated = SimplePagination(suppliers_list[start:end], page, per_page, total)

    suppliers_with_counts = []
    for supplier in suppliers_paginated.items:
        spec_count = Specification.query.filter_by(supplier_id=supplier.id).count()
        suppliers_with_counts.append({
            'supplier': supplier,
            'spec_count': spec_count
        })

    return render_template('suppliers.html',
                           current_user=user,
                           suppliers=suppliers_with_counts,
                           pagination=suppliers_paginated,
                           search_query=search_query,
                           material_filter=material_filter,
                           materials_options=sorted(materials_options.values(), key=str.lower))


@suppliers_bp.route('/suppliers/create', methods=['POST'])
@login_required
def create():
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'message': 'Sessão inválida'}), 401

    try:
        data = request.get_json()

        supplier = Supplier()
        supplier.user_id = user.id
        supplier.name = data.get('name')
        supplier.location = data.get('location')
        supplier.contact_name = data.get('contact_name')
        supplier.contact_email = data.get('contact_email')
        supplier.contact_phone = data.get('contact_phone')
        supplier.materials_json = json.dumps(data.get('materials', []))
        supplier.avatar_color = data.get('avatar_color', '#667eea')

        db.session.add(supplier)
        db.session.commit()
        
        log_activity('CREATE_SUPPLIER', 'supplier', supplier.id, target_name=supplier.name)
        rpa_info(f"CREATE_SUPPLIER: Fornecedor '{supplier.name}' criado (ID: {supplier.id})")

        return jsonify({
            'success': True,
            'message': 'Fornecedor criado com sucesso!',
            'supplier_id': supplier.id
        })
    except Exception as e:
        db.session.rollback()
        rpa_error(f"CREATE_SUPPLIER_ERRO: Erro ao criar fornecedor", exc=e, regiao="fornecedores")
        print(f"Error creating supplier: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@suppliers_bp.route('/suppliers/<int:id>', methods=['GET'])
@login_required
def get(id):
    supplier = Supplier.query.get_or_404(id)
    user = User.query.get(session['user_id'])

    if not user.is_admin and supplier.user_id != user.id:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403

    return jsonify({
        'id': supplier.id,
        'name': supplier.name,
        'location': supplier.location,
        'contact_name': supplier.contact_name,
        'contact_email': supplier.contact_email,
        'contact_phone': supplier.contact_phone,
        'materials': json.loads(supplier.materials_json) if supplier.materials_json else [],
        'avatar_color': supplier.avatar_color
    })


@suppliers_bp.route('/suppliers/<int:id>/products', methods=['GET'])
@login_required
def products(id):
    supplier = Supplier.query.get_or_404(id)
    user = User.query.get(session['user_id'])

    if not user:
        return jsonify({'success': False, 'message': 'SessÇœo invÇ­lida'}), 401
    if not user.is_admin and supplier.user_id != user.id:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403

    specs = (Specification.query
             .filter_by(supplier_id=supplier.id)
             .order_by(Specification.created_at.desc())
             .all())

    products = []
    for spec in specs:
        products.append({
            'id': spec.id,
            'ref': spec.ref_souq,
            'name': spec.description or spec.pdf_filename,
            'status': spec.status or 'draft',
            'thumbnail': spec.pdf_thumbnail or spec.technical_drawing_url,
        })

    return jsonify({
        'success': True,
        'supplier_id': supplier.id,
        'supplier_name': supplier.name,
        'products': products,
    })


@suppliers_bp.route('/suppliers/<int:id>/update', methods=['POST'])
@login_required
def update(id):
    supplier = Supplier.query.get_or_404(id)
    user = User.query.get(session['user_id'])

    if not user.is_admin and supplier.user_id != user.id:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403

    try:
        data = request.get_json()

        supplier.name = data.get('name', supplier.name)
        supplier.location = data.get('location', supplier.location)
        supplier.contact_name = data.get('contact_name', supplier.contact_name)
        supplier.contact_email = data.get('contact_email', supplier.contact_email)
        supplier.contact_phone = data.get('contact_phone', supplier.contact_phone)
        supplier.materials_json = json.dumps(data.get('materials', []))
        supplier.avatar_color = data.get('avatar_color', supplier.avatar_color)

        db.session.commit()
        
        log_activity('EDIT_SUPPLIER', 'supplier', supplier.id, target_name=supplier.name)
        rpa_info(f"EDIT_SUPPLIER: Fornecedor '{supplier.name}' atualizado (ID: {supplier.id})")

        return jsonify({
            'success': True,
            'message': 'Fornecedor atualizado com sucesso!'
        })
    except Exception as e:
        db.session.rollback()
        rpa_error(f"EDIT_SUPPLIER_ERRO: Erro ao atualizar fornecedor", exc=e, regiao="fornecedores")
        print(f"Error updating supplier: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@suppliers_bp.route('/suppliers/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    supplier = Supplier.query.get_or_404(id)
    user = User.query.get(session['user_id'])

    if not user.is_admin and supplier.user_id != user.id:
        return jsonify({'success': False, 'message': 'Acesso negado'}), 403

    try:
        supplier_name = supplier.name
        db.session.delete(supplier)
        db.session.commit()
        log_activity('DELETE_SUPPLIER', 'supplier', id, target_name=supplier_name)
        rpa_info(f"DELETE_SUPPLIER: Fornecedor '{supplier_name}' excluído (ID: {id})")
        return jsonify({
            'success': True,
            'message': 'Fornecedor excluído com sucesso!'
        })
    except Exception as e:
        db.session.rollback()
        rpa_error(f"DELETE_SUPPLIER_ERRO: Erro ao excluir fornecedor ID {id}", exc=e, regiao="fornecedores")
        print(f"Error deleting supplier: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
