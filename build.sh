#!/bin/bash

echo "🔨 Building production version..."

export REACT_APP_API_URL=https://pomnyasha.ru/api

npm run build

echo "✅ Build complete! Files are in ./build directory"
echo "📦 Upload build/* to /var/www/pomnyasha.ru/frontend/ on your server"

