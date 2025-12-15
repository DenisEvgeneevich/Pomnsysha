# Проверка интеграции с GigaChat и чат-эндпоинта

Ниже — минимальные шаги, чтобы вручную убедиться, что новый конвейер разбора задач работает.

## Подготовка backend
1. Перейдите в директорию `backend` и создайте виртуальное окружение:
   ```bash
   cd backend
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Пропишите ключ авторизации GigaChat в файле `.env` (см. `backend/GIGACHAT_SETUP.txt`).
   ```bash
   echo "GIGACHAT_AUTHORIZATION_KEY=ваш_ключ" > .env
   ```

## Запуск backend
1. Запустите API:
   ```bash
   uvicorn app:app --reload
   ```
2. После старта сервер доступен на `http://localhost:8000`.

## Ручная проверка эндпоинта `/chat`
1. В отдельном терминале выполните запрос:
   ```bash
   curl -X POST http://localhost:8000/chat \
     -H 'Content-Type: application/json' \
     -d '{"message": "совещание с командой завтра в 11:00"}'
   ```
2. Убедитесь, что в ответе есть поле `reply.processed_task` со структурой:
   ```json
   {
     "title": "Совещание с командой",
     "date": "2024-10-23",
     "time": "11:00",
     "category": "Работа",
     "priority": "medium"
   }
   ```
   и что обёртка `reply` содержит `success: true`, исходный текст и предупреждения (если применимо).

## Проверка фронтенда (опционально)
1. В корне проекта установите зависимости и запустите dev-сервер:
   ```bash
   npm install
   npm start
   ```
2. В интерфейсе откройте вкладку чата, отправьте тестовую фразу и убедитесь, что карточка события создаётся по возвращённому JSON.
