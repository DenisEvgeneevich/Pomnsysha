#!/bin/bash

set -e

SERVER_USER="${1:-root}"
SERVER_HOST="${2:-pomnyasha.ru}"
APP_DIR="/var/www/pomnyasha.ru"

echo "🚀 Setting up Pomnyasha on server..."

ssh $SERVER_USER@$SERVER_HOST << 'ENDSSH'
set -e

APP_DIR="/var/www/pomnyasha.ru"

echo "📦 Installing Python dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

echo "📁 Setting up directories..."
mkdir -p $APP_DIR/frontend
mkdir -p $APP_DIR/backend
mkdir -p $APP_DIR/backend/secrets
chown -R www-data:www-data $APP_DIR

echo "🐍 Setting up Python virtual environment..."
cd $APP_DIR/backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "⚙️ Setting up systemd services..."
cp pomnyasha-backend.service /etc/systemd/system/
cp pomnyasha-bot.service /etc/systemd/system/
systemctl daemon-reload

echo "🌐 Setting up nginx..."
cp /tmp/pomnyasha-nginx.conf /etc/nginx/sites-available/pomnyasha.ru
ln -sf /etc/nginx/sites-available/pomnyasha.ru /etc/nginx/sites-enabled/
nginx -t

echo "✅ Server setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Edit $APP_DIR/backend/.env with your credentials"
echo "2. Start services: sudo systemctl start pomnyasha-backend pomnyasha-bot"
echo "3. Enable services: sudo systemctl enable pomnyasha-backend pomnyasha-bot"
echo "4. Setup SSL: sudo certbot --nginx -d pomnyasha.ru -d www.pomnyasha.ru"
echo "5. Reload nginx: sudo systemctl reload nginx"
ENDSSH

echo "✅ Setup script completed!"

