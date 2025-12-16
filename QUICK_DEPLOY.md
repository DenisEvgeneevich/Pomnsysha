# 🚀 Быстрый деплой на pomnyasha.ru

## Шаг 1: Сборка Frontend

```bash
# В корне проекта
export REACT_APP_API_URL=https://pomnyasha.ru/api
npm run build
```

Или используйте готовый скрипт:
```bash
bash build.sh
```

## Шаг 2: Подготовка файлов для загрузки

### Что нужно загрузить на сервер:

1. **Frontend**: папка `build/` → `/var/www/pomnyasha.ru/frontend/`
2. **Backend**: папка `backend/` → `/var/www/pomnyasha.ru/backend/`

## Шаг 3: Настройка на сервере

### Backend:

```bash
cd /var/www/pomnyasha.ru/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Создайте .env файл
cat > .env << EOF
GIGACHAT_AUTHORIZATION_KEY=your_key_here
TELEGRAM_BOT_TOKEN=8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4
DATABASE_URL=sqlite:///app.db
REDIRECT_URI=https://pomnyasha.ru/api/oauth2/callback
FRONTEND_URL=https://pomnyasha.ru
EOF

# Запустите через systemd (см. DEPLOY.md)
```

### Nginx:

Используйте `nginx.conf.example` как основу для конфигурации.

## Шаг 4: Настройка Mini App в @BotFather

1. Откройте @BotFather
2. `/newapp` или выберите бота → Mini App
3. **Web App URL**: `https://pomnyasha.ru`

## ✅ Готово!

После деплоя проверьте:
- https://pomnyasha.ru - открывается приложение
- https://pomnyasha.ru/api/events - API работает
- Mini App в Telegram открывается корректно

