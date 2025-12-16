#!/bin/bash

set -e

echo "🔨 Building production version..."

export REACT_APP_API_URL=https://pomnyasha.ru/api

npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo "✅ Build complete!"
echo ""
echo "📦 Next steps:"
echo "1. Upload build/* to /var/www/pomnyasha.ru/frontend/ on your server"
echo "2. Upload backend/* to /var/www/pomnyasha.ru/backend/ on your server"
echo "3. Follow instructions in DEPLOY.md"

