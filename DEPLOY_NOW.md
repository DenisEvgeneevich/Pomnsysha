# 🚀 ДЕПЛОЙ СЕЙЧАС - Пошаговая инструкция

## ✅ Что уже готово:

1. ✅ Production build собран (папка `build/`)
2. ✅ Backend файлы готовы
3. ✅ Все скрипты созданы
4. ✅ Конфигурации подготовлены

## 📤 ШАГ 1: Загрузка файлов на сервер

### Вариант A: Через WinSCP/FileZilla (Windows)

1. Откройте WinSCP или FileZilla
2. Подключитесь к серверу pomnyasha.ru
3. Загрузите файлы:

**Frontend:**
- Выберите все файлы из папки `build/`
- Загрузите в: `/var/www/pomnyasha.ru/frontend/`

**Backend:**
- Выберите всю папку `backend/` (кроме venv и __pycache__)
- Загрузите в: `/var/www/pomnyasha.ru/backend/`

### Вариант B: Через SSH/SCP (Linux/Mac)

```bash
# Frontend
scp -r build/* user@pomnyasha.ru:/var/www/pomnyasha.ru/frontend/

# Backend (исключая venv и __pycache__)
scp -r backend/*.py backend/requirements.txt backend/secrets user@pomnyasha.ru:/var/www/pomnyasha.ru/backend/
scp backend/pomnyasha-*.service user@pomnyasha.ru:/tmp/
```

## 🔧 ШАГ 2: Настройка на сервере

Подключитесь по SSH и выполните:

```bash
# 1. Перейдите в директорию backend
cd /var/www/pomnyasha.ru/backend

# 2. Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# 3. Установите зависимости
pip install --upgrade pip
pip install -r requirements.txt

# 4. Создайте .env файл
cat > .env << 'EOF'
GIGACHAT_AUTHORIZATION_KEY=your_key_here
TELEGRAM_BOT_TOKEN=8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4
DATABASE_URL=sqlite:///app.db
REDIRECT_URI=https://pomnyasha.ru/api/oauth2/callback
FRONTEND_URL=https://pomnyasha.ru
EOF

# 5. Отредактируйте .env (замените your_key_here на реальный ключ)
nano .env

# 6. Установите права
chown -R www-data:www-data /var/www/pomnyasha.ru
chmod -R 755 /var/www/pomnyasha.ru/frontend
```

## ⚙️ ШАГ 3: Настройка systemd сервисов

```bash
# Скопируйте файлы сервисов
sudo cp /tmp/pomnyasha-backend.service /etc/systemd/system/
sudo cp /tmp/pomnyasha-bot.service /etc/systemd/system/

# Или если файлы уже в backend/
sudo cp /var/www/pomnyasha.ru/backend/pomnyasha-backend.service /etc/systemd/system/
sudo cp /var/www/pomnyasha.ru/backend/pomnyasha-bot.service /etc/systemd/system/

# Перезагрузите systemd
sudo systemctl daemon-reload

# Запустите сервисы
sudo systemctl start pomnyasha-backend
sudo systemctl start pomnyasha-bot

# Включите автозапуск
sudo systemctl enable pomnyasha-backend
sudo systemctl enable pomnyasha-bot

# Проверьте статус
sudo systemctl status pomnyasha-backend
sudo systemctl status pomnyasha-bot
```

## 🌐 ШАГ 4: Настройка Nginx

```bash
# Скопируйте конфигурацию
sudo cp nginx.conf.example /etc/nginx/sites-available/pomnyasha.ru

# Или создайте вручную (см. nginx.conf.example)

# Создайте симлинк
sudo ln -s /etc/nginx/sites-available/pomnyasha.ru /etc/nginx/sites-enabled/

# Проверьте конфигурацию
sudo nginx -t

# Перезагрузите nginx
sudo systemctl reload nginx
```

## 🔐 ШАГ 5: Настройка SSL

```bash
# Установите certbot (если еще не установлен)
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

# Получите SSL сертификат
sudo certbot --nginx -d pomnyasha.ru -d www.pomnyasha.ru

# Certbot автоматически обновит nginx конфигурацию
```

## ✅ ШАГ 6: Проверка

```bash
# Проверьте, что сервисы работают
sudo systemctl status pomnyasha-backend
sudo systemctl status pomnyasha-bot

# Проверьте логи
sudo journalctl -u pomnyasha-backend -f
sudo journalctl -u pomnyasha-bot -f

# Проверьте порты
sudo netstat -tlnp | grep 8000
```

Откройте в браузере:
- ✅ https://pomnyasha.ru - должно открываться приложение
- ✅ https://pomnyasha.ru/api/events - должен возвращать JSON

## 🤖 ШАГ 7: Настройка Telegram Mini App

1. Откройте @BotFather в Telegram
2. Отправьте `/newapp` или выберите бота → Mini App
3. Укажите:
   - **Web App URL**: `https://pomnyasha.ru`
   - **Title**: Помняша
   - **Short name**: pomnyasha

## 🎉 Готово!

Ваше приложение должно быть доступно на https://pomnyasha.ru и работать в Telegram Mini App!

## 🔄 Обновление кода

После изменений:

```bash
# Локально: пересоберите
cd todo-app
$env:REACT_APP_API_URL="https://pomnyasha.ru/api"
npm run build

# Загрузите только измененные файлы на сервер
scp -r build/* user@pomnyasha.ru:/var/www/pomnyasha.ru/frontend/

# Перезапустите backend (если изменили backend)
ssh user@pomnyasha.ru "sudo systemctl restart pomnyasha-backend"
```

