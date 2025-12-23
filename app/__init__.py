import os
from flask import Flask
from app.config import config
from app.extensions import db, csrf, init_openai
from app.routes import register_blueprints
from app.utils.logging import init_rpa_monitor


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    app.config.from_object(config[config_name])
    
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs('static/thumbnails', exist_ok=True)
    os.makedirs('static/drawings', exist_ok=True)
    os.makedirs('static/covers', exist_ok=True)
    os.makedirs('static/product_images', exist_ok=True)
    
    db.init_app(app)
    csrf.init_app(app)
    
    init_openai(app.config.get('OPENAI_API_KEY'))
    
    # RPA Monitor temporariamente desabilitado - pacote rpa_monitor_client com problema de conexao
    # Para reativar, descomente o bloco abaixo e corrija o pacote rpa_monitor_client
    # rpa_host = app.config.get('RPA_MONITOR_HOST', '')
    # if app.config.get('RPA_MONITOR_ID') and rpa_host:
    #     try:
    #         host_parts = rpa_host.replace('ws://', '').replace('wss://', '').split(':')
    #         host = host_parts[0]
    #         port = int(host_parts[1]) if len(host_parts) > 1 else 443
    #         init_rpa_monitor(
    #             rpa_id=app.config['RPA_MONITOR_ID'],
    #             host=host,
    #             port=port,
    #             region=app.config.get('RPA_MONITOR_REGION', 'default'),
    #             transport=app.config.get('RPA_MONITOR_TRANSPORT', 'ws')
    #         )
    #     except Exception as e:
    #         print(f"RPA Monitor initialization skipped: {e}")
    
    register_blueprints(app)
    
    @app.after_request
    def add_cache_control(response):
        if 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
    
    return app


def init_db(app):
    from app.models import User
    from app.utils.logging import rpa_info
    
    with app.app_context():
        db.create_all()
        
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User()
            admin.username = 'admin'
            admin.email = 'admin@example.com'
            admin.is_admin = True
            admin.role = 'admin'
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created: username='admin', password='admin123'")
        
        rpa_info("SISTEMA: StyleSheet PLM iniciado com sucesso")
