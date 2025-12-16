# Деплой на pomnyasha.ru

## 📋 Подготовка к деплою

### 1. Структура на сервере

```
/var/www/pomnyasha.ru/
├── frontend/          # React build
├── backend/           # Python FastAPI
└── nginx.conf         # Конфигурация nginx
```

### 2. Backend (FastAPI)

#### Настройка на сервере:

```bash
# Создайте директорию
mkdir -p /var/www/pomnyasha.ru/backend
cd /var/www/pomnyasha.ru/backend

# Скопируйте файлы backend
# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install -r requirements.txt

# Создайте .env файл
nano .env
```

#### Содержимое `.env`:
```
GIGACHAT_AUTHORIZATION_KEY=your_key
TELEGRAM_BOT_TOKEN=8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4
DATABASE_URL=sqlite:///app.db
REDIRECT_URI=https://pomnyasha.ru/api/oauth2/callback
```

#### Запуск через systemd:

Создайте `/etc/systemd/system/pomnyasha-backend.service`:
```ini
[Unit]
Description=Pomnyasha Backend API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/pomnyasha.ru/backend
Environment="PATH=/var/www/pomnyasha.ru/backend/venv/bin"
ExecStart=/var/www/pomnyasha.ru/backend/venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pomnyasha-backend
sudo systemctl start pomnyasha-backend
```

### 3. Frontend (React)

#### Сборка production версии:

```bash
cd /path/to/your/project
npm install
REACT_APP_API_URL=https://pomnyasha.ru/api npm run build
```

#### Загрузка на сервер:

```bash
# Скопируйте папку build на сервер
scp -r build/* user@pomnyasha.ru:/var/www/pomnyasha.ru/frontend/
```

### 4. Nginx конфигурация

Создайте `/etc/nginx/sites-available/pomnyasha.ru`:

```nginx
server {
    listen 80;
    server_name pomnyasha.ru www.pomnyasha.ru;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name pomnyasha.ru www.pomnyasha.ru;

    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/key.pem;

    # Frontend (React)
    location / {
        root /var/www/pomnyasha.ru/frontend;
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-cache";
    }

    # Backend API
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Telegram-User-ID $http_x_telegram_user_id;
    }

    # Статические файлы
    location /static {
        root /var/www/pomnyasha.ru/frontend;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/pomnyasha.ru /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5. SSL сертификат (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d pomnyasha.ru -d www.pomnyasha.ru
```

## 🚀 Быстрый деплой

### Вариант 1: Через Git

```bash
# На сервере
cd /var/www/pomnyasha.ru
git clone https://your-repo.git .

# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Отредактируйте .env

# Frontend
cd ../frontend
npm install
REACT_APP_API_URL=https://pomnyasha.ru/api npm run build
```

### Вариант 2: Ручная загрузка

1. Соберите frontend локально:
   ```bash
   REACT_APP_API_URL=https://pomnyasha.ru/api npm run build
   ```

2. Загрузите файлы на сервер через FTP/SFTP:
   - `build/*` → `/var/www/pomnyasha.ru/frontend/`
   - `backend/*` → `/var/www/pomnyasha.ru/backend/`

## ✅ Проверка после деплоя

1. Проверьте frontend: https://pomnyasha.ru
2. Проверьте API: https://pomnyasha.ru/api/events
3. Проверьте Telegram Mini App в @BotFather

## 🔧 Обновление кода

После изменений:

```bash
# Frontend
npm run build
scp -r build/* user@pomnyasha.ru:/var/www/pomnyasha.ru/frontend/

# Backend
scp -r backend/* user@pomnyasha.ru:/var/www/pomnyasha.ru/backend/
ssh user@pomnyasha.ru "sudo systemctl restart pomnyasha-backend"
```

## 📝 Важные моменты

- ✅ Backend должен работать на `127.0.0.1:8000` (не публично)
- ✅ Nginx проксирует `/api` на backend
- ✅ Frontend должен использовать `https://pomnyasha.ru/api` для запросов
- ✅ SSL обязателен для Telegram Mini App
- ✅ CORS настроен для домена pomnyasha.ru

