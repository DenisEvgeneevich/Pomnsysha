# Настройка Telegram Mini App

## Как работает интеграция

### 1. Архитектура:
```
Telegram Mini App (ваш React код)
    ↓
Telegram WebApp API (window.Telegram.WebApp)
    ↓ передает user_id в заголовке
Backend API (FastAPI)
    ↓ использует user_id для идентификации
SQLite Database (каждый user_id изолирован)
```

### 2. Поток данных:

**Когда пользователь открывает мини-приложение:**
1. Telegram автоматически загружает ваш React код
2. Telegram WebApp API предоставляет данные пользователя через `window.Telegram.WebApp`
3. Ваш код получает `user_id` и передает его в заголовке `X-Telegram-User-ID` при каждом запросе к backend
4. Backend использует этот `user_id` для идентификации пользователя и работы с его данными

### 3. Настройка в @BotFather:

1. Откройте @BotFather в Telegram
2. Отправьте команду `/newapp` или выберите вашего бота и `/mybots` → выберите бота → "Bot Settings" → "Mini App"
3. Укажите:
   - **Title**: Помняша
   - **Short name**: pomnyasha (или другое уникальное)
   - **Web App URL**: `https://your-domain.com` (или `http://localhost:3000` для тестирования)
   - **Description**: ИИ-ассистент для планирования задач

### 4. Для локального тестирования:

Используйте ngrok или аналогичный сервис для создания публичного URL:

```bash
# Установите ngrok
ngrok http 3000

# Используйте полученный URL (например, https://abc123.ngrok.io) в @BotFather
```

### 5. Что происходит в коде:

**Frontend (React):**
- `src/utils/telegramWebApp.js` - получает данные пользователя из Telegram
- `src/utils/session.js` - добавляет заголовок `X-Telegram-User-ID` к каждому запросу
- Все компоненты автоматически используют эту интеграцию

**Backend (FastAPI):**
- `backend/app.py` - читает заголовок `X-Telegram-User-ID` 
- Автоматически создает пользователя в БД при первом обращении
- Все события привязываются к этому `user_id`

### 6. Проверка работы:

1. Откройте бота в Telegram
2. Нажмите на кнопку "Mini App" (или отправьте команду `/start` если настроена кнопка)
3. Откройте консоль браузера (F12) - вы должны увидеть:
   ```javascript
   window.Telegram.WebApp.initDataUnsafe.user.id // ваш user_id
   ```

### 7. Важные моменты:

- ✅ Каждый пользователь изолирован по своему `telegram_user_id`
- ✅ Google Calendar опционален - можно работать без него
- ✅ Все данные сохраняются в SQLite локально
- ✅ Для продакшена нужен HTTPS (Telegram требует безопасное соединение)

### 8. Добавление кнопки Mini App в бота:

В `backend/telegram_bot.py` можно добавить кнопку:

```python
from telegram import KeyboardButton, ReplyKeyboardMarkup

keyboard = [[KeyboardButton("Открыть приложение", web_app=WebAppInfo(url="https://your-domain.com"))]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
await update.message.reply_text("Нажмите кнопку ниже", reply_markup=reply_markup)
```

## Текущий токен бота:
`8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4`

Токен уже интегрирован в `backend/telegram_bot.py`

