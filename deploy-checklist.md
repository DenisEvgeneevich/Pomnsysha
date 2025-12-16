# ✅ Чеклист деплоя на pomnyasha.ru

## 📦 Подготовка файлов

- [ ] Собрать frontend: `REACT_APP_API_URL=https://pomnyasha.ru/api npm run build`
- [ ] Проверить, что папка `build/` создана
- [ ] Подготовить backend файлы

## 🖥️ Настройка сервера

### Backend
- [ ] Создать директорию `/var/www/pomnyasha.ru/backend`
- [ ] Загрузить файлы backend
- [ ] Создать виртуальное окружение: `python3 -m venv venv`
- [ ] Установить зависимости: `pip install -r requirements.txt`
- [ ] Создать `.env` файл с правильными значениями
- [ ] Настроить systemd service (см. DEPLOY.md)
- [ ] Запустить backend: `sudo systemctl start pomnyasha-backend`

### Frontend
- [ ] Создать директорию `/var/www/pomnyasha.ru/frontend`
- [ ] Загрузить содержимое папки `build/` в frontend директорию
- [ ] Проверить права доступа: `chmod -R 755 /var/www/pomnyasha.ru/frontend`

### Nginx
- [ ] Установить nginx (если не установлен)
- [ ] Создать конфигурацию из `nginx.conf.example`
- [ ] Настроить SSL сертификат (Let's Encrypt)
- [ ] Проверить конфигурацию: `sudo nginx -t`
- [ ] Перезагрузить nginx: `sudo systemctl reload nginx`

## 🔐 SSL сертификат

- [ ] Установить certbot: `sudo apt install certbot python3-certbot-nginx`
- [ ] Получить сертификат: `sudo certbot --nginx -d pomnyasha.ru -d www.pomnyasha.ru`
- [ ] Проверить автообновление: `sudo certbot renew --dry-run`

## 🤖 Telegram Mini App

- [ ] Открыть @BotFather
- [ ] Настроить Mini App с URL: `https://pomnyasha.ru`
- [ ] Проверить открытие Mini App в Telegram

## ✅ Проверка работы

- [ ] https://pomnyasha.ru - открывается приложение
- [ ] https://pomnyasha.ru/api/events - API отвечает
- [ ] Telegram Mini App открывается корректно
- [ ] Авторизация Google работает
- [ ] Создание событий работает

## 🔧 Переменные окружения

Убедитесь, что в `.env` на сервере:
```
GIGACHAT_AUTHORIZATION_KEY=your_key
TELEGRAM_BOT_TOKEN=8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4
DATABASE_URL=sqlite:///app.db
REDIRECT_URI=https://pomnyasha.ru/api/oauth2/callback
FRONTEND_URL=https://pomnyasha.ru
```

