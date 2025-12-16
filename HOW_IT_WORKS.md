# Как ваш код передается в Telegram Mini App

## 📱 Процесс работы:

### 1. **Ваш React код → Telegram Mini App**

Когда вы настраиваете Mini App в @BotFather:
- Вы указываете URL вашего React приложения (например, `https://your-domain.com`)
- Telegram загружает ваш код и отображает его внутри Telegram
- Это обычный веб-сайт, который открывается внутри Telegram

### 2. **Telegram передает данные пользователя**

Telegram автоматически:
- Загружает скрипт `telegram-web-app.js` (уже добавлен в `public/index.html`)
- Предоставляет данные через `window.Telegram.WebApp`
- Ваш код получает `user_id` пользователя

### 3. **Ваш код отправляет запросы к Backend**

В каждом запросе к API:
- `src/utils/telegramWebApp.js` получает `user_id` из Telegram
- `src/utils/session.js` добавляет заголовок `X-Telegram-User-ID`
- Backend использует этот `user_id` для идентификации

## 🔄 Поток данных:

```
Telegram Mini App (React)
    ↓
window.Telegram.WebApp.initDataUnsafe.user.id
    ↓
getTelegramHeaders() → добавляет заголовок X-Telegram-User-ID
    ↓
fetch('/chat', { headers: { 'X-Telegram-User-ID': '123456789' } })
    ↓
Backend (FastAPI) читает заголовок
    ↓
ensure_user_exists(user_id) → создает пользователя в БД
    ↓
Все события сохраняются с этим user_id
```

## ✅ Что уже сделано:

1. ✅ Добавлен скрипт Telegram WebApp в `public/index.html`
2. ✅ Создан `src/utils/telegramWebApp.js` для получения данных пользователя
3. ✅ Обновлен `src/utils/session.js` для передачи заголовков
4. ✅ Обновлен `src/components/ChatPage.jsx` для использования Telegram заголовков
5. ✅ Backend уже читает заголовок `X-Telegram-User-ID`
6. ✅ Токен бота обновлен: `8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4`

## 🚀 Что нужно сделать:

### Шаг 1: Настроить Mini App в @BotFather

1. Откройте @BotFather в Telegram
2. Отправьте `/newapp` или выберите вашего бота → `/mybots` → выберите бота → "Bot Settings" → "Mini App"
3. Заполните:
   - **Title**: Помняша
   - **Short name**: pomnyasha
   - **Web App URL**: `https://your-domain.com` (для продакшена) или используйте ngrok для локального тестирования
   - **Description**: ИИ-ассистент для планирования задач

### Шаг 2: Для локального тестирования (ngrok)

```bash
# Установите ngrok: https://ngrok.com/
ngrok http 3000

# Используйте полученный URL (например, https://abc123.ngrok.io) в @BotFather
```

### Шаг 3: Запустить приложение

```bash
# Backend (уже запущен)
cd backend
python app.py

# Frontend (в другом терминале)
npm start

# Telegram Bot (уже запущен)
cd backend
python run_bot.py
```

## 🔍 Проверка работы:

1. Откройте бота в Telegram
2. Нажмите кнопку Mini App (или отправьте `/start`)
3. Откройте консоль браузера (F12) и проверьте:
   ```javascript
   window.Telegram.WebApp.initDataUnsafe.user.id
   // Должен показать ваш user_id
   ```

4. Проверьте Network tab - в заголовках запросов должен быть:
   ```
   X-Telegram-User-ID: 123456789
   ```

## 📝 Важно:

- ✅ Каждый пользователь изолирован по своему `telegram_user_id`
- ✅ Google Calendar опционален
- ✅ Все данные сохраняются в SQLite локально
- ✅ Для продакшена нужен HTTPS (Telegram требует безопасное соединение)

## 🎯 Итого:

Ваш код **уже готов** для работы в Telegram Mini App! Просто:
1. Настройте Mini App в @BotFather
2. Укажите URL вашего приложения
3. Готово! Пользователи смогут открыть ваше приложение прямо в Telegram

