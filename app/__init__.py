import os
import json
from dotenv import load_dotenv, dotenv_values
from flask import Flask
from app.config import config
from app.extensions import db, csrf, init_openai
from app.routes import register_blueprints
from app.utils.logging import init_rpa_monitor


def create_app(config_name=None):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    app_env = os.environ.get('APP_ENV') or os.environ.get('FLASK_ENV') or 'development'
    env_key = app_env.strip().lower()

    if env_key in {'prod', 'production'}:
        env_filename = '.env.prod'
    elif env_key in {'dev', 'development', 'local'}:
        env_filename = '.env.local'
    else:
        env_filename = '.env'

    env_path = os.path.join(base_dir, env_filename)
    fallback_env_path = os.path.join(base_dir, '.env')

    active_env_path = None
    if os.path.exists(env_path):
        active_env_path = env_path
    elif os.path.exists(fallback_env_path):
        active_env_path = fallback_env_path

    if active_env_path:
        load_dotenv(active_env_path, override=True)

    if not os.environ.get('DATABASE_URL') and active_env_path:
        for key, value in dotenv_values(active_env_path).items():
            if value is not None and not os.environ.get(key):
                os.environ[key] = value
        if not os.environ.get('DATABASE_URL'):
            with open(active_env_path, 'r', encoding='utf-8') as env_file:
                for raw_line in env_file:
                    line = raw_line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and not os.environ.get(key):
                        os.environ[key] = value
    if config_name is None:
        if env_key in {'prod', 'production'}:
            config_name = 'production'
        elif env_key in {'dev', 'development', 'local'}:
            config_name = 'development'
        else:
            config_name = os.environ.get('FLASK_ENV', 'default')
    
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    app.config.from_object(config[config_name])
    app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY')
    app.config['RPA_MONITOR_ID'] = os.environ.get('RPA_MONITOR_ID')
    app.config['RPA_MONITOR_HOST'] = os.environ.get('RPA_MONITOR_HOST')
    app.config['RPA_MONITOR_REGION'] = os.environ.get('RPA_MONITOR_REGION', 'default')
    app.config['RPA_MONITOR_TRANSPORT'] = os.environ.get('RPA_MONITOR_TRANSPORT', 'ws')
    
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.static_folder, 'thumbnails'), exist_ok=True)
    os.makedirs(os.path.join(app.static_folder, 'drawings'), exist_ok=True)
    os.makedirs(os.path.join(app.static_folder, 'covers'), exist_ok=True)
    os.makedirs(os.path.join(app.static_folder, 'product_images'), exist_ok=True)
    
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
    
    def _from_json(value):
        if not value:
            return []
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []

    app.jinja_env.filters['from_json'] = _from_json
    
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
