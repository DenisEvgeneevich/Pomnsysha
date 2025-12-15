import os
import requests
import uuid
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")
ACCESS_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

TOKEN_CACHE = None

# Функции для работы с календарем и анализом запросов
def parse_event_request(message: str) -> dict:
    """
    Анализирует сообщение пользователя на предмет запроса создания события.
    Возвращает dict с распознанными параметрами или None если не найдено.
    """
    message = message.lower().strip()

    # Паттерны для распознавания дат
    date_patterns = {
        'сегодня': 0,
        'завтра': 1,
        'послезавтра': 2,
        'через день': 1,
        'через два дня': 2,
        'через три дня': 3,
        'через неделю': 7
    }

    # Ищем дату в сообщении
    target_date = None
    for pattern, days_offset in date_patterns.items():
        if pattern in message:
            target_date = (datetime.now() + timedelta(days=days_offset)).date()
            break

    # Ищем числовые даты (дд.мм, дд.мм.гггг)
    date_match = re.search(r'(\d{1,2})[.\-](\d{1,2})(?:[.\-](\d{2,4}))?', message)
    if date_match:
        day, month = int(date_match.group(1)), int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else datetime.now().year

        # Корректируем год если нужно
        if year < 100:
            year += 2000

        try:
            target_date = datetime(year, month, day).date()
        except ValueError:
            pass  # Неверная дата

    if not target_date:
        return None

    # Ищем время в сообщении (если указано)
    time_match = re.search(r'(\d{1,2})[:\.](\d{2})', message)
    requested_time = None
    if time_match:
        hours, minutes = int(time_match.group(1)), int(time_match.group(2))
        try:
            requested_time = datetime.strptime(f"{hours:02d}:{minutes:02d}", "%H:%M").time()
        except ValueError:
            pass

    # Ищем описание события (убираем слова о дате и времени)
    description = message
    for pattern in date_patterns.keys():
        description = description.replace(pattern, '')

    description = re.sub(r'\d{1,2}[.\-:]\d{1,2}(?:[.\-]\d{2,4})?', '', description)  # Убираем даты
    description = re.sub(r'\d{1,2}[:\.]\d{2}', '', description)  # Убираем время
    description = re.sub(r'\s+', ' ', description).strip()  # Убираем лишние пробелы

    # Убираем общие слова
    remove_words = ['поставь', 'создай', 'заплань', 'добавь', 'сделай', 'на', 'в', 'во', 'к', 'на', 'около']
    for word in remove_words:
        description = description.replace(f' {word} ', ' ')

    description = description.strip()

    return {
        'date': target_date,
        'time': requested_time,
        'description': description or 'Событие'
    }

def get_free_slots_for_date(date, existing_events):
    """
    Находит свободные временные слоты на заданную дату.
    Возвращает список доступных временных интервалов.
    """
    # Рабочие часы: 9:00 - 18:00
    work_start = datetime.combine(date, datetime.strptime("09:00", "%H:%M").time())
    work_end = datetime.combine(date, datetime.strptime("18:00", "%H:%M").time())

    # Сортируем существующие события по времени
    sorted_events = sorted(existing_events, key=lambda x: x.start_time)

    free_slots = []
    current_time = work_start

    for event in sorted_events:
        event_start = event.start_time
        event_end = event.end_time or event.start_time  # Если end_time не указан, считаем событие точечным

        # Если событие начинается после текущего времени, добавляем свободный слот
        if event_start > current_time:
            slot_duration = (event_start - current_time).total_seconds() / 3600  # в часах
            if slot_duration >= 0.5:  # Минимум 30 минут
                free_slots.append({
                    'start': current_time,
                    'end': event_start,
                    'duration_hours': slot_duration
                })

        # Обновляем текущее время на конец события
        current_time = max(current_time, event_end)

    # Добавляем слот после последнего события до конца рабочего дня
    if current_time < work_end:
        slot_duration = (work_end - current_time).total_seconds() / 3600
        if slot_duration >= 0.5:
            free_slots.append({
                'start': current_time,
                'end': work_end,
                'duration_hours': slot_duration
            })

    return free_slots

def suggest_optimal_time(date, description, existing_events):
    """
    Предлагает оптимальное время для события на основе занятости и типа события.
    """
    free_slots = get_free_slots_for_date(date, existing_events)

    if not free_slots:
        return None

    # Анализируем тип события для выбора оптимального времени
    event_type = description.lower()

    if any(word in event_type for word in ['встреча', 'совещание', 'митинг', 'meeting']):
        # Для встреч предпочитаем утро или середину дня
        preferred_slots = [slot for slot in free_slots if slot['duration_hours'] >= 1.0]
        if preferred_slots:
            # Выбираем слот в первой половине дня
            morning_slots = [s for s in preferred_slots if s['start'].hour < 14]
            if morning_slots:
                return morning_slots[0]['start']
            return preferred_slots[0]['start']

    elif any(word in event_type for word in ['обед', 'перерыв', 'пауза']):
        # Для обедов - время обеда
        lunch_slots = [slot for slot in free_slots
                      if 12 <= slot['start'].hour <= 15 and slot['duration_hours'] >= 1.0]
        if lunch_slots:
            return lunch_slots[0]['start']

    elif any(word in event_type for word in ['спорт', 'тренировка', 'бег']):
        # Для спорта - вечер или утро
        evening_slots = [slot for slot in free_slots
                        if slot['start'].hour >= 17 and slot['duration_hours'] >= 1.0]
        morning_slots = [slot for slot in free_slots
                        if 7 <= slot['start'].hour <= 10 and slot['duration_hours'] >= 1.0]
        if evening_slots:
            return evening_slots[0]['start']
        elif morning_slots:
            return morning_slots[0]['start']

    # Для остальных событий - просто первый доступный слот достаточной длительности
    suitable_slots = [slot for slot in free_slots if slot['duration_hours'] >= 0.5]
    if suitable_slots:
        return suitable_slots[0]['start']

    return None


def get_token():
    global TOKEN_CACHE
    if TOKEN_CACHE:
        return TOKEN_CACHE

    if not AUTHORIZATION_KEY or AUTHORIZATION_KEY == "YOUR_GIGACHAT_AUTH_KEY_HERE":
        return None

    try:
        rquid = str(uuid.uuid4())
        r = requests.post(
            ACCESS_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": rquid,
                "Authorization": f"Bearer {AUTHORIZATION_KEY}"
            },
            data={"scope": "GIGACHAT_API_PERS"},
            verify=False,
            timeout=10
        )

        if r.status_code != 200:
            return None

        response_data = r.json()
        TOKEN_CACHE = response_data.get("access_token")
        if not TOKEN_CACHE:
            return None

        return TOKEN_CACHE
    except Exception:
        return None


def ask_gigachat(message: str, db_session=None, user_id=None) -> dict:
    """
    Расширенная версия ask_gigachat, которая может обрабатывать запросы на создание событий.
    Возвращает dict с типом ответа и данными.
    """
    # Перезагружаем переменные окружения при каждом вызове
    load_dotenv()
    global AUTHORIZATION_KEY
    AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

    # Сбрасываем кэш токена при каждом вызове для надежности
    global TOKEN_CACHE
    TOKEN_CACHE = None

    # Сначала проверяем, является ли сообщение запросом на создание события
    if db_session and user_id:
        event_request = parse_event_request(message)
        if event_request:
            # Это запрос на создание события
            target_date = event_request['date']
            description = event_request['description']

            # Получаем существующие события на эту дату
            from database import Event
            existing_events = db_session.query(Event).filter(
                Event.user_id == user_id,
                Event.start_time >= datetime.combine(target_date, datetime.min.time()),
                Event.start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            ).all()

            # Предлагаем оптимальное время
            suggested_time = suggest_optimal_time(target_date, description, existing_events)

            if suggested_time:
                return {
                    'type': 'event_suggestion',
                    'data': {
                        'date': target_date,
                        'description': description,
                        'suggested_time': suggested_time,
                        'free_slots_count': len(get_free_slots_for_date(target_date, existing_events))
                    }
                }
            else:
                return {
                    'type': 'text',
                    'content': f"Извините, на {target_date.strftime('%d.%m.%Y')} нет свободного времени для события '{description}'. Попробуйте выбрать другую дату."
                }

    # Если это не запрос на событие или нет доступа к БД, обращаемся к GigaChat
    token = get_token()
    if not token:
        return {
            'type': 'text',
            'content': "ИИ помощник не настроен. Создайте файл .env с GIGACHAT_AUTHORIZATION_KEY (см. GIGACHAT_SETUP.txt)"
        }

    try:
        r = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "GigaChat",
                "messages": [
                    {"role": "system", "content": "Ты — Помняша, ИИ помощник-планировщик. Помогаешь с организацией времени и планированием задач."},
                    {"role": "user", "content": message}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            },
            verify=False,
            timeout=20
        )

        if r.status_code != 200:
            TOKEN_CACHE = None
            return {
                'type': 'text',
                'content': f"Ошибка API GigaChat (код {r.status_code})"
            }

        response_data = r.json()
        if "choices" not in response_data or not response_data["choices"]:
            return {
                'type': 'text',
                'content': "Ошибка формата ответа GigaChat"
            }

        return {
            'type': 'text',
            'content': response_data["choices"][0]["message"]["content"]
        }

    except Exception as e:
        return {
            'type': 'text',
            'content': f"Ошибка соединения с GigaChat: {str(e)}"
        }