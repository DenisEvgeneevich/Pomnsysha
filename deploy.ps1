$env:REACT_APP_API_URL = "https://pomnyasha.ru/api"

Write-Host "🔨 Building production version..." -ForegroundColor Cyan
npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Build complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📦 Next steps:" -ForegroundColor Yellow
Write-Host "1. Upload build/* to /var/www/pomnyasha.ru/frontend/ on your server"
Write-Host "2. Upload backend/* to /var/www/pomnyasha.ru/backend/ on your server"
Write-Host "3. Configure environment variables and services on the server"
