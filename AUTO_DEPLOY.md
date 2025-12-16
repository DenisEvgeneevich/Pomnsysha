# 🚀 Автоматический деплой на pomnyasha.ru

## Быстрый старт (Windows PowerShell)

```powershell
# 1. Соберите production build
cd todo-app
$env:REACT_APP_API_URL="https://pomnyasha.ru/api"
npm run build

# 2. Загрузите файлы на сервер (замените user и host)
# Через WinSCP, FileZilla или scp:
# - build/* → /var/www/pomnyasha.ru/frontend/
# - backend/* → /var/www/pomnyasha.ru/backend/
```

## Автоматический деплой через SSH (Linux/Mac)

```bash
# 1. Соберите build
cd todo-app
export REACT_APP_API_URL=https://pomnyasha.ru/api
npm run build

# 2. Запустите автоматический деплой
chmod +x server-setup.sh setup-server.sh
./server-setup.sh your_user pomnyasha.ru
./setup-server.sh your_user pomnyasha.ru
```

## Ручной деплой

### Шаг 1: Подготовка файлов

```powershell
# Windows
cd todo-app
$env:REACT_APP_API_URL="https://pomnyasha.ru/api"
npm run build
```

### Шаг 2: Загрузка на сервер

Используйте WinSCP, FileZilla или любой FTP/SFTP клиент:

**Frontend:**
- Загрузите все файлы из папки `build/` 
- В директорию: `/var/www/pomnyasha.ru/frontend/`

**Backend:**
- Загрузите всю папку `backend/`
- В директорию: `/var/www/pomnyasha.ru/backend/`

### Шаг 3: Настройка на сервере

Подключитесь к серверу по SSH и выполните:

```bash
# Перейдите в директорию backend
cd /var/www/pomnyasha.ru/backend

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Создайте .env файл
nano .env
```

Вставьте в `.env`:
```
GIGACHAT_AUTHORIZATION_KEY=your_key_here
TELEGRAM_BOT_TOKEN=8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4
DATABASE_URL=sqlite:///app.db
REDIRECT_URI=https://pomnyasha.ru/api/oauth2/callback
FRONTEND_URL=https://pomnyasha.ru
```

```bash
# Настройте systemd сервисы
sudo cp pomnyasha-backend.service /etc/systemd/system/
sudo cp pomnyasha-bot.service /etc/systemd/system/
sudo systemctl daemon-reload

# Запустите сервисы
sudo systemctl start pomnyasha-backend
sudo systemctl start pomnyasha-bot
sudo systemctl enable pomnyasha-backend
sudo systemctl enable pomnyasha-bot

# Настройте nginx
sudo cp nginx.conf.example /etc/nginx/sites-available/pomnyasha.ru
sudo ln -s /etc/nginx/sites-available/pomnyasha.ru /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Настройте SSL (если еще не настроен)
sudo certbot --nginx -d pomnyasha.ru -d www.pomnyasha.ru
```

## Проверка

После деплоя проверьте:
- ✅ https://pomnyasha.ru - открывается приложение
- ✅ https://pomnyasha.ru/api/events - API работает
- ✅ Telegram Mini App открывается

## Обновление кода

После изменений:

```powershell
# Пересоберите
cd todo-app
$env:REACT_APP_API_URL="https://pomnyasha.ru/api"
npm run build

# Загрузите только измененные файлы на сервер
```

