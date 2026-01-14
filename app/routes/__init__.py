from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.admin import admin_bp
from app.routes.specifications import specifications_bp
from app.routes.collections import collections_bp
from app.routes.suppliers import suppliers_bp
from app.routes.drawings import drawings_bp
from app.routes.settings import settings_bp
from app.routes.api import api_bp
from app.routes.fichas import fichas_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(specifications_bp)
    app.register_blueprint(collections_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(drawings_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(fichas_bp)
