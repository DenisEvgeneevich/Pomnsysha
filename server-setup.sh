#!/bin/bash

set -e

SERVER_USER="${1:-root}"
SERVER_HOST="${2:-pomnyasha.ru}"
APP_DIR="/var/www/pomnyasha.ru"

echo "🚀 Setting up server: $SERVER_USER@$SERVER_HOST"

ssh $SERVER_USER@$SERVER_HOST << EOF
set -e

echo "📁 Creating directories..."
mkdir -p $APP_DIR/frontend
mkdir -p $APP_DIR/backend
mkdir -p $APP_DIR/backend/secrets

echo "✅ Directories created"
EOF

echo "📤 Uploading files..."

echo "Uploading frontend..."
scp -r build/* $SERVER_USER@$SERVER_HOST:$APP_DIR/frontend/

echo "Uploading backend..."
scp -r backend/* $SERVER_USER@$SERVER_HOST:$APP_DIR/backend/

echo "Uploading nginx config..."
scp nginx.conf.example $SERVER_USER@$SERVER_HOST:/tmp/pomnyasha-nginx.conf

echo "✅ Files uploaded"
echo ""
echo "🔧 Next steps on server:"
echo "1. cd $APP_DIR/backend"
echo "2. python3 -m venv venv"
echo "3. source venv/bin/activate"
echo "4. pip install -r requirements.txt"
echo "5. Create .env file with your credentials"
echo "6. Setup systemd services"
echo "7. Configure nginx using /tmp/pomnyasha-nginx.conf"
