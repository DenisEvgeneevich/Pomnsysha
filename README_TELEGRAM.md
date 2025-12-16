# Telegram Bot Setup

## Установка зависимостей
```bash
pip install python-telegram-bot==20.7
```

## Настройка
1. Создайте бота через @BotFather в Telegram
2. Получите токен бота
3. Добавьте токен в `.env` файл:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

## Запуск
```bash
python backend/run_bot.py
```

## Функционал
- `/start` - приветствие и список команд
- `/events` - показать события
- `/stats` - статистика по категориям и дням недели
- `/sync` - синхронизировать с Google Calendar
- Отправка сообщений - ИИ обрабатывает задачи и предлагает время
- Кнопки подтверждения для создания событий

