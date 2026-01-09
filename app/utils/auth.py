from functools import wraps
from flask import session, redirect, url_for, flash


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        from app.models import User
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Admin access required.')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function
