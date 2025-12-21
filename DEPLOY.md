# Инструкция по деплою Pomnsysha на Ubuntu VPS

## Тип проекта
- **Frontend**: React (react-scripts)
- **Backend**: FastAPI (Python 3.11+) с uvicorn
- **База данных**: SQLite
- **Веб-сервер**: Nginx (reverse proxy)

---

## A) Production Build

### 1. Подготовка переменных окружения

Создайте файлы `.env` на основе примеров:

**Backend (.env в корне проекта):**
```bash
HOST=0.0.0.0
PORT=8000
REDIRECT_URI=https://yourdomain.com/oauth2/callback
CORS_ORIGINS=https://yourdomain.com
DATABASE_URL=sqlite:///./app.db
DEBUG=false
```

**Frontend (.env в корне проекта для build):**
```bash
REACT_APP_API_URL=https://yourdomain.com
```

### 2. Сборка Frontend

```bash
# Установка зависимостей
npm install

# Production build
npm run build
```

Результат будет в папке `build/`.

### 3. Проверка Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

---

## B) Вариант 1: Деплой без Docker

### Шаг 1: Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
sudo apt install -y python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx git
```

### Шаг 2: Создание пользователя и структуры каталогов

```bash
# Создание пользователя (если нужно)
sudo adduser --disabled-password --gecos "" pomnsysha

# Создание структуры каталогов
sudo mkdir -p /var/www/pomnsysha/{backend,frontend,venv,data}
sudo chown -R $USER:$USER /var/www/pomnsysha
```

### Шаг 3: Клонирование и настройка проекта

```bash
cd /var/www/pomnsysha

# Клонирование репозитория (или загрузка файлов)
git clone <your-repo-url> . || scp -r /path/to/project/* .

# Создание виртуального окружения для Python
python3.11 -m venv venv
source venv/bin/activate

# Установка зависимостей backend
cd backend
pip install -r requirements.txt
cd ..
```

### Шаг 4: Настройка Backend

```bash
# Создание .env файла для backend
cat > /var/www/pomnsysha/backend/.env << EOF
HOST=127.0.0.1
PORT=8000
REDIRECT_URI=https://yourdomain.com/oauth2/callback
CORS_ORIGINS=https://yourdomain.com
DATABASE_URL=sqlite:///./app.db
DEBUG=false
EOF

# Копирование secrets (если есть)
# cp -r /path/to/secrets /var/www/pomnsysha/backend/

# Инициализация базы данных
cd /var/www/pomnsysha/backend
python init_db.py  # если есть скрипт инициализации
cd ..
```

### Шаг 5: Настройка Frontend

```bash
# Установка Node.js (если не установлен)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Установка зависимостей и сборка
cd /var/www/pomnsysha
npm install

# Создание .env для build
echo "REACT_APP_API_URL=https://yourdomain.com" > .env

# Production build
npm run build

# Копирование build в нужное место
cp -r build/* /var/www/pomnsysha/frontend/build/
```

### Шаг 6: Настройка Systemd Service

```bash
# Копирование unit файла
sudo cp pomnsysha.service /etc/systemd/system/

# Редактирование (замените example.com на ваш домен)
sudo nano /etc/systemd/system/pomnsysha.service

# Перезагрузка systemd и запуск
sudo systemctl daemon-reload
sudo systemctl enable pomnsysha.service
sudo systemctl start pomnsysha.service

# Проверка статуса
sudo systemctl status pomnsysha.service

# Просмотр логов
sudo journalctl -u pomnsysha.service -f
```

### Шаг 7: Настройка Nginx

```bash
# Копирование конфигурации
sudo cp nginx-site.conf /etc/nginx/sites-available/pomnsysha

# Редактирование (замените example.com на ваш домен)
sudo nano /etc/nginx/sites-available/pomnsysha

# Создание симлинка
sudo ln -s /etc/nginx/sites-available/pomnsysha /etc/nginx/sites-enabled/

# Удаление default конфига (опционально)
sudo rm /etc/nginx/sites-enabled/default

# Проверка конфигурации
sudo nginx -t

# Перезагрузка Nginx
sudo systemctl reload nginx
```

### Шаг 8: Настройка SSL (Let's Encrypt)

```bash
# Получение сертификата
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Автоматическое обновление (уже настроено в cron)
sudo certbot renew --dry-run
```

### Шаг 9: Настройка прав доступа

```bash
# Права для веб-сервера
sudo chown -R www-data:www-data /var/www/pomnsysha/frontend/build
sudo chown -R www-data:www-data /var/www/pomnsysha/backend
sudo chown -R www-data:www-data /var/www/pomnsysha/data

# Права на выполнение
sudo chmod +x /var/www/pomnsysha/venv/bin/uvicorn
```

---

## C) Вариант 2: Деплой с Docker

### Шаг 1: Установка Docker и Docker Compose

```bash
# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезагрузка сессии
newgrp docker
```

### Шаг 2: Подготовка проекта

```bash
# Создание директории
sudo mkdir -p /var/www/pomnsysha
cd /var/www/pomnsysha

# Клонирование или загрузка файлов
git clone <your-repo-url> . || scp -r /path/to/project/* .

# Создание .env файла
cat > .env << EOF
REDIRECT_URI=https://yourdomain.com/oauth2/callback
CORS_ORIGINS=https://yourdomain.com
REACT_APP_API_URL=https://yourdomain.com
DEBUG=false
EOF
```

### Шаг 3: Сборка и запуск

```bash
# Сборка образов
docker-compose build

# Запуск контейнеров
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f
```

### Шаг 4: Настройка Nginx (для Docker)

Если используете Docker, Nginx должен проксировать на `localhost:80` (frontend) и `localhost:8000` (backend).

Создайте `/etc/nginx/sites-available/pomnsysha-docker`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Шаг 5: Обновление приложения

```bash
cd /var/www/pomnsysha

# Остановка
docker-compose down

# Обновление кода
git pull  # или загрузка новых файлов

# Пересборка и запуск
docker-compose up -d --build
```

---

## D) Healthcheck и логи

### Healthcheck Endpoint

Backend предоставляет endpoint `/health`:

```bash
# Проверка здоровья
curl http://localhost:8000/health

# Ответ:
# {"status":"healthy","service":"pomnsysha-backend","timestamp":"2024-..."}
```

### Логи

**Systemd (без Docker):**
```bash
# Логи backend
sudo journalctl -u pomnsysha.service -f

# Последние 100 строк
sudo journalctl -u pomnsysha.service -n 100
```

**Docker:**
```bash
# Логи всех сервисов
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f backend
docker-compose logs -f frontend
```

**Nginx:**
```bash
# Access log
sudo tail -f /var/log/nginx/pomnsysha-access.log

# Error log
sudo tail -f /var/log/nginx/pomnsysha-error.log
```

### Мониторинг

```bash
# Проверка процессов
ps aux | grep uvicorn
ps aux | grep nginx

# Проверка портов
sudo netstat -tlnp | grep -E '8000|80|443'

# Проверка использования ресурсов
htop
df -h
```

---

## E) Итоговый список файлов

### Добавленные/измененные файлы:

1. **`Dockerfile.backend`** - Docker образ для backend
2. **`Dockerfile.frontend`** - Docker образ для frontend (multi-stage)
3. **`docker-compose.yml`** - Docker Compose конфигурация
4. **`nginx.conf`** - Nginx конфиг для Docker frontend
5. **`nginx-site.conf`** - Nginx server block для production (без Docker)
6. **`pomnsysha.service`** - Systemd unit файл для backend
7. **`DEPLOY.md`** - Эта инструкция
8. **`backend/app.py`** - Добавлен `/health` endpoint и поддержка env переменных

### Файлы для создания вручную:

- `.env` - переменные окружения для backend
- `.env` (в корне) - переменные окружения для frontend build

---

## Быстрая инструкция "копипастой" для чистого Ubuntu VPS

```bash
# 1. Обновление системы
sudo apt update && sudo apt upgrade -y

# 2. Установка зависимостей
sudo apt install -y python3.11 python3.11-venv python3-pip nginx certbot python3-certbot-nginx git curl

# 3. Установка Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# 4. Создание структуры
sudo mkdir -p /var/www/pomnsysha/{backend,frontend,venv,data}
sudo chown -R $USER:$USER /var/www/pomnsysha

# 5. Переход в директорию
cd /var/www/pomnsysha

# 6. Загрузка проекта (замените на ваш способ)
# git clone <your-repo> . || scp -r /path/to/project/* .

# 7. Настройка Python окружения
python3.11 -m venv venv
source venv/bin/activate
cd backend && pip install -r requirements.txt && cd ..

# 8. Настройка Frontend
npm install
echo "REACT_APP_API_URL=https://yourdomain.com" > .env
npm run build
cp -r build/* frontend/build/

# 9. Настройка Backend .env
cat > backend/.env << EOF
HOST=127.0.0.1
PORT=8000
REDIRECT_URI=https://yourdomain.com/oauth2/callback
CORS_ORIGINS=https://yourdomain.com
DATABASE_URL=sqlite:///./app.db
DEBUG=false
EOF

# 10. Настройка Systemd
sudo cp pomnsysha.service /etc/systemd/system/
sudo nano /etc/systemd/system/pomnsysha.service  # Замените example.com
sudo systemctl daemon-reload
sudo systemctl enable pomnsysha.service
sudo systemctl start pomnsysha.service

# 11. Настройка Nginx
sudo cp nginx-site.conf /etc/nginx/sites-available/pomnsysha
sudo nano /etc/nginx/sites-available/pomnsysha  # Замените example.com
sudo ln -s /etc/nginx/sites-available/pomnsysha /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 12. SSL сертификат
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# 13. Права доступа
sudo chown -R www-data:www-data /var/www/pomnsysha/frontend/build
sudo chown -R www-data:www-data /var/www/pomnsysha/backend
sudo chown -R www-data:www-data /var/www/pomnsysha/data

# 14. Проверка
curl http://localhost:8000/health
sudo systemctl status pomnsysha.service
```

---

## Обновление приложения

### Без Docker:
```bash
cd /var/www/pomnsysha
git pull  # или загрузка новых файлов
source venv/bin/activate
cd backend && pip install -r requirements.txt && cd ..
npm install
npm run build
cp -r build/* frontend/build/
sudo systemctl restart pomnsysha.service
sudo systemctl reload nginx
```

### С Docker:
```bash
cd /var/www/pomnsysha
git pull  # или загрузка новых файлов
docker-compose down
docker-compose up -d --build
```

---

## Troubleshooting

1. **Backend не запускается:**
   - Проверьте логи: `sudo journalctl -u pomnsysha.service -n 50`
   - Проверьте .env файл
   - Проверьте права доступа

2. **Nginx ошибки:**
   - Проверьте конфиг: `sudo nginx -t`
   - Проверьте логи: `sudo tail -f /var/log/nginx/error.log`

3. **Порт занят:**
   - Проверьте: `sudo netstat -tlnp | grep 8000`
   - Остановите конфликтующий процесс

4. **CORS ошибки:**
   - Проверьте CORS_ORIGINS в .env
   - Убедитесь, что домен указан правильно

---

Готово! Ваше приложение должно быть доступно по адресу https://yourdomain.com



