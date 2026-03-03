from app import create_app, init_db

app = create_app()
init_db(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
