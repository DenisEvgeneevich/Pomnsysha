# Помняша - ИИ-ассистент для планирования

Мини-приложение для Telegram бота с полным функционалом планирования задач.

## Возможности

- ИИ-ассистент для создания задач через естественный язык
- Интеллектуальный подбор времени с учетом занятости
- Автоматическое присвоение категорий задачам
- Синхронизация с Google Calendar
- Статистика по категориям и дням недели
- Календарь с метками категорий
- Мобильная адаптация

## Установка

### Backend

```bash
cd backend
pip install -r requirements.txt
```

Создайте `.env` файл:
```
GIGACHAT_AUTHORIZATION_KEY=your_key
TELEGRAM_BOT_TOKEN=your_bot_token
DATABASE_URL=sqlite:///app.db
REDIRECT_URI=http://localhost:8000/oauth2/callback
```

### Frontend

```bash
npm install
```

## Запуск

### Backend (FastAPI)
```bash
cd backend
python app.py
```

### Telegram Bot
```bash
cd backend
python run_bot.py
```

### Frontend (React)
```bash
npm start
```
