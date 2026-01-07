"""
StyleSheet PLM - Aplicação Principal (Legado)

Este arquivo foi modularizado. Todo o código foi movido para a estrutura:
    app/
    ├── __init__.py          # Factory pattern (create_app, init_db)
    ├── config.py            # Configurações por ambiente
    ├── extensions.py        # SQLAlchemy, CSRF, OpenAI
    ├── models/              # Modelos SQLAlchemy
    ├── forms/               # Formulários Flask-WTF
    ├── routes/              # Blueprints Flask
    └── utils/               # Utilitários compartilhados

Ponto de entrada principal: run.py

Este arquivo mantido para compatibilidade.
Para executar: python run.py
"""

from app import create_app, init_db

# Criar instância da aplicação usando factory pattern
app = create_app()  

# Inicializar banco de dados
init_db(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
