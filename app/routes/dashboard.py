from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from app.extensions import db
from app.models import User, Specification
from app.utils.auth import login_required

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    search_query = request.args.get('search', '').strip()
    selected_collection = request.args.get('collection', '')
    selected_supplier = request.args.get('supplier', '')
    selected_status = request.args.get('status', '')

    if user.is_admin:
        total_users = User.query.count()
        total_specs = Specification.query.count()

        query = Specification.query

        if search_query:
            search_filter = f'%{search_query}%'
            query = query.filter(
                db.or_(Specification.description.ilike(search_filter),
                       Specification.ref_souq.ilike(search_filter),
                       Specification.collection.ilike(search_filter),
                       Specification.pdf_filename.ilike(search_filter)))

        if selected_collection:
            query = query.filter_by(collection=selected_collection)

        if selected_supplier:
            query = query.filter_by(supplier=selected_supplier)

        if selected_status:
            query = query.filter_by(status=selected_status)

        recent_specs = query.order_by(Specification.created_at.desc()).limit(100).all()

        collections = db.session.query(Specification.collection).distinct().filter(
            Specification.collection.isnot(None)).all()
        collections = [c[0] for c in collections if c[0]]

        suppliers = db.session.query(Specification.supplier).distinct().filter(
            Specification.supplier.isnot(None)).all()
        suppliers = [s[0] for s in suppliers if s[0]]

        return render_template('admin_dashboard.html',
                               current_user=user,
                               total_users=total_users,
                               total_specs=total_specs,
                               recent_specs=recent_specs,
                               collections=collections,
                               suppliers=suppliers,
                               selected_collection=selected_collection,
                               selected_supplier=selected_supplier,
                               selected_status=selected_status,
                               search_query=search_query)
    else:
        query = Specification.query.filter_by(user_id=user.id)

        if search_query:
            search_filter = f'%{search_query}%'
            query = query.filter(
                db.or_(Specification.description.ilike(search_filter),
                       Specification.ref_souq.ilike(search_filter),
                       Specification.collection.ilike(search_filter),
                       Specification.pdf_filename.ilike(search_filter)))

        if selected_collection:
            query = query.filter_by(collection=selected_collection)

        if selected_supplier:
            query = query.filter_by(supplier=selected_supplier)

        if selected_status:
            query = query.filter_by(status=selected_status)

        user_specs = query.order_by(Specification.created_at.desc()).limit(100).all()

        collections = db.session.query(Specification.collection).distinct().filter(
            Specification.collection.isnot(None),
            Specification.user_id == user.id).all()
        collections = [c[0] for c in collections if c[0]]

        suppliers = db.session.query(Specification.supplier).distinct().filter(
            Specification.supplier.isnot(None),
            Specification.user_id == user.id).all()
        suppliers = [s[0] for s in suppliers if s[0]]

        return render_template('user_dashboard.html',
                               current_user=user,
                               specifications=user_specs,
                               collections=collections,
                               suppliers=suppliers,
                               selected_collection=selected_collection,
                               selected_supplier=selected_supplier,
                               selected_status=selected_status,
                               search_query=search_query)
