#!/bin/bash
# ══════════════════════════════════════════════════════════
# AutoPLM — Deploy Script para Google Cloud VM (Ubuntu/Debian)
# ══════════════════════════════════════════════════════════
set -e

APP_NAME="autoplm"
APP_DIR="/opt/$APP_NAME"
APP_USER="autoplm"
PYTHON_VERSION="3.13"
DOMAIN=""  # Preencha se tiver domínio, ex: autoplm.seudominio.com

echo "═══════════════════════════════════════════"
echo "  AutoPLM — Deploy Script"
echo "═══════════════════════════════════════════"

# 1. System packages
echo "📦 [1/7] Instalando dependências do sistema..."
sudo apt update && sudo apt install -y \
    python3 python3-pip python3-venv \
    nginx \
    tesseract-ocr tesseract-ocr-por \
    poppler-utils \
    git curl

# 2. Create app user
echo "👤 [2/7] Criando usuário da aplicação..."
if ! id "$APP_USER" &>/dev/null; then
    sudo useradd -r -s /bin/false -m -d $APP_DIR $APP_USER
fi

# 3. Setup app directory
echo "📁 [3/7] Configurando diretório..."
sudo mkdir -p $APP_DIR
sudo cp -r . $APP_DIR/
sudo mkdir -p $APP_DIR/uploads
sudo mkdir -p $APP_DIR/static/thumbnails
sudo mkdir -p /var/log/$APP_NAME

# 4. Python venv + deps
echo "🐍 [4/7] Criando virtualenv e instalando dependências..."
sudo python3 -m venv $APP_DIR/venv
sudo $APP_DIR/venv/bin/pip install --upgrade pip
sudo $APP_DIR/venv/bin/pip install -r $APP_DIR/requirements.txt

# 5. .env
echo "⚙️ [5/7] Configurando .env..."
if [ ! -f $APP_DIR/.env ]; then
    sudo cp $APP_DIR/.env.example $APP_DIR/.env
    echo "  ⚠️  EDITE O ARQUIVO .env COM SUAS CREDENCIAIS:"
    echo "     sudo nano $APP_DIR/.env"
fi

# 6. Systemd service
echo "🔧 [6/7] Configurando serviço systemd..."
sudo tee /etc/systemd/system/$APP_NAME.service > /dev/null <<EOF
[Unit]
Description=AutoPLM Flask Application
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
Restart=always
RestartSec=5
StandardOutput=append:/var/log/$APP_NAME/app.log
StandardError=append:/var/log/$APP_NAME/error.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $APP_NAME

# 7. Nginx
echo "🌐 [7/7] Configurando Nginx..."
SERVER_NAME=${DOMAIN:-"_"}
sudo tee /etc/nginx/sites-available/$APP_NAME > /dev/null <<EOF
server {
    listen 80;
    server_name $SERVER_NAME;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }

    location /static/ {
        alias $APP_DIR/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Permissions
sudo chown -R $APP_USER:$APP_USER $APP_DIR
sudo chown -R $APP_USER:$APP_USER /var/log/$APP_NAME

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ Deploy concluído!"
echo "═══════════════════════════════════════════"
echo ""
echo "  PRÓXIMOS PASSOS:"
echo "  1. Edite o .env:  sudo nano $APP_DIR/.env"
echo "  2. Inicie o app:  sudo systemctl start $APP_NAME"
echo "  3. Verifique:     sudo systemctl status $APP_NAME"
echo "  4. Logs:          sudo tail -f /var/log/$APP_NAME/app.log"
echo ""
echo "  Acesse: http://$(curl -s ifconfig.me 2>/dev/null || echo 'SEU_IP')"
echo ""
