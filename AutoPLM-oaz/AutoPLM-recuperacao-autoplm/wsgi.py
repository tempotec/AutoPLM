"""WSGI entry point for production (Gunicorn)."""
from app import create_app, init_db

app = create_app()
init_db(app)
