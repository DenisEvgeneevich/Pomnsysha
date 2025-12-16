# 🎯 ФИНАЛЬНЫЕ ИНСТРУКЦИИ ПО ДЕПЛОЮ

## ✅ ВСЕ ГОТОВО К ДЕПЛОЮ!

Все файлы подготовлены. Следуйте инструкциям ниже.

## 📋 ЧТО НУЖНО СДЕЛАТЬ:

### 1️⃣ Загрузите файлы на сервер pomnyasha.ru

**Через WinSCP/FileZilla:**
- Папка `build/` → `/var/www/pomnyasha.ru/frontend/`
- Папка `backend/` → `/var/www/pomnyasha.ru/backend/` (кроме venv и __pycache__)

**Или через команду (Linux/Mac):**
```bash
scp -r build/* user@pomnyasha.ru:/var/www/pomnyasha.ru/frontend/
scp -r backend/*.py backend/requirements.txt backend/secrets backend/pomnyasha-*.service user@pomnyasha.ru:/var/www/pomnyasha.ru/backend/
```

### 2️⃣ Подключитесь к серверу по SSH

```bash
ssh user@pomnyasha.ru
```

### 3️⃣ Выполните команды на сервере

```bash
# Перейдите в backend
cd /var/www/pomnyasha.ru/backend

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установите зависимости
pip install --upgrade pip
pip install -r requirements.txt

# Создайте .env файл
cat > .env << 'EOF'
GIGACHAT_AUTHORIZATION_KEY=ваш_ключ_здесь
TELEGRAM_BOT_TOKEN=8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4
DATABASE_URL=sqlite:///app.db
REDIRECT_URI=https://pomnyasha.ru/api/oauth2/callback
FRONTEND_URL=https://pomnyasha.ru
EOF

# Отредактируйте .env - замените ваш_ключ_здесь на реальный ключ
nano .env

# Установите права
sudo chown -R www-data:www-data /var/www/pomnyasha.ru
sudo chmod -R 755 /var/www/pomnyasha.ru/frontend

# Настройте systemd сервисы
sudo cp pomnyasha-backend.service /etc/systemd/system/
sudo cp pomnyasha-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
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

### 4️⃣ Проверьте работу

- Откройте https://pomnyasha.ru
- Проверьте https://pomnyasha.ru/api/events
- Настройте Mini App в @BotFather с URL: https://pomnyasha.ru

## 🎉 ГОТОВО!

Ваше приложение работает на pomnyasha.ru!

## 📞 Если нужна помощь:

- Проверьте логи: `sudo journalctl -u pomnyasha-backend -f`
- Проверьте nginx: `sudo nginx -t`
- Проверьте статус: `sudo systemctl status pomnyasha-backend`

