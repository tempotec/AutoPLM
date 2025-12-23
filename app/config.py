import os


class Config:
    SECRET_KEY = os.environ.get('SESSION_SECRET')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
        'pool_timeout': 30,
    }
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 1024 * 1024 * 1024  # 1GB max file size
    
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    
    RPA_MONITOR_ID = os.environ.get("RPA_MONITOR_ID")
    RPA_MONITOR_HOST = os.environ.get("RPA_MONITOR_HOST")
    RPA_MONITOR_REGION = os.environ.get("RPA_MONITOR_REGION", "default")
    RPA_MONITOR_TRANSPORT = os.environ.get("RPA_MONITOR_TRANSPORT", "ws")


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
