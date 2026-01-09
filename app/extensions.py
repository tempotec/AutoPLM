from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from openai import OpenAI

db = SQLAlchemy()
csrf = CSRFProtect()

openai_client = None

def init_openai(api_key):
    global openai_client
    if api_key:
        openai_client = OpenAI(api_key=api_key)
    return openai_client

def get_openai_client():
    return openai_client
