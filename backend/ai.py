import json
import os
import re
import uuid
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")
ACCESS_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

TOKEN_CACHE = None

CATEGORIES = ["Работа", "Учеба", "Личное", "Здоровье", "Покупки", "Встречи"]
PRIORITIES = {"high", "medium", "low"}

# Функции для работы с календарем и анализом запросов
def _today_with_weekday():
    now = datetime.now()
    weekdays = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ]
    return now.date(), weekdays[now.weekday()]


def _build_gigachat_prompt(user_text: str) -> str:
    today_date, weekday = _today_with_weekday()
    return f"""
Ты — интеллектуальный помощник для планирования. Твоя задача — анализировать короткие текстовые заметки пользователя на русском языке и извлекать из них структурированные данные для создания события в календаре.

ПРАВИЛА АНАЛИЗА:
1.  СЕГОДНЯШНЯЯ ДАТА: {today_date:%Y-%m-%d} ({weekday}). Все относительные даты ("завтра", "через неделю") вычисляй относительно неё.
2.  НАЗВАНИЕ: Сформулируй краткое (3-7 слов), четкое и понятное название задачи или события на русском языке, используя ключевые слова из заметки. Убери мусорные слова ("надо", "не забыть").
3.  ДАТА и ВРЕМЯ: Извлеки ВСЕ упоминания дат и времени. Если дата явно не указана, считай, что событие должно произойти СЕГОДНЯ. Если время не указано, укажи null.
4.  КАТЕГОРИЯ: Выбери ОДНУ из: {CATEGORIES}. Определяй по контексту.
5.  ПРИОРИТЕТ: Определи по тону и ключевым словам:
    - "high" (высокий): если есть слова "срочно", "важно", "критично", "!!!", "очень надо".
    - "medium" (средний): по умолчанию, для нейтральных поручений.
    - "low" (низкий): если есть слова "не срочно", "когда будет время", "может быть".

ФОРМАТ ОТВЕТА:
Ты должен ответить ТОЛЬКО в виде JSON-объекта, строго по следующей схеме:
{{
  "title": "string",
  "date": "YYYY-MM-DD",
  "time": "HH:MM или null",
  "category": "string из списка выше",
  "priority": "high/medium/low"
}}

НИКАКОГО пояснительного текста, только JSON.

ТЕКСТ ПОЛЬЗОВАТЕЛЯ ДЛЯ АНАЛИЗА: "{user_text}"
"""


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


def _normalize_title(title: str) -> str:
    if not title:
        return "Без названия"
    cleaned = title.strip()
    return cleaned[:1].upper() + cleaned[1:]


def _safe_json_loads(raw):
    """
    Пытается безопасно распарсить JSON из ответа модели,
    даже если вокруг есть пояснительный текст или обёртки.
    """
    def _unwrap_collection(value):
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
        return value

    unwrapped = _unwrap_collection(raw)
    if isinstance(unwrapped, dict):
        return unwrapped

    if not isinstance(raw, str):
        return None

    candidates = [raw, re.sub(r"```json|```", "", raw).strip()]

    decoder = json.JSONDecoder()

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            return _unwrap_collection(parsed)
        except json.JSONDecodeError:
            pass

        brace_index = candidate.find("{")
        while brace_index != -1:
            try:
                obj, _ = decoder.raw_decode(candidate[brace_index:])
                return _unwrap_collection(obj)
            except json.JSONDecodeError:
                brace_index = candidate.find("{", brace_index + 1)

    return None


def _validate_and_enrich(parsed: dict, original_text: str) -> tuple[bool, dict, list[str]]:
    warnings: list[str] = []
    today, _ = _today_with_weekday()

    if not parsed or not isinstance(parsed, dict):
        return False, None, ["Модель вернула невалидный JSON"]

    title = _normalize_title(parsed.get("title"))
    date_str = parsed.get("date")
    time_str = parsed.get("time")
    category = parsed.get("category")
    priority = parsed.get("priority")

    if category not in CATEGORIES:
        warnings.append("Категория заменена на 'Личное'")
        category = "Личное"

    if priority not in PRIORITIES:
        warnings.append("Приоритет установлен по умолчанию (medium)")
        priority = "medium"

    parsed_date = None
    was_date_parsed = False
    if isinstance(date_str, str):
        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            was_date_parsed = True
        except ValueError:
            warnings.append("Дата не распознана, используется сегодняшняя")
    else:
        warnings.append("Дата не указана, используется сегодняшняя")

    if not parsed_date:
        parsed_date = today

    if parsed_date < today:
        warnings.append("Дата была в прошлом и сдвинута на сегодня")
        parsed_date = today

    parsed_time = None
    has_time = False
    if isinstance(time_str, str):
        try:
            parsed_time = datetime.strptime(time_str, "%H:%M").time()
            has_time = True
        except ValueError:
            warnings.append("Время не распознано и сброшено")
    elif time_str is not None:
        warnings.append("Время имеет неверный формат, сброшено")

    datetime_iso = None
    if parsed_time:
        datetime_iso = datetime.combine(parsed_date, parsed_time).isoformat()

    processed_task = {
        "title": title,
        "description": f"Сгенерировано из заметки: '{original_text}'",
        "date": parsed_date.isoformat(),
        "time": parsed_time.strftime("%H:%M") if parsed_time else None,
        "datetime_iso": datetime_iso,
        "category": category,
        "priority": priority,
        "is_full_day_event": not bool(parsed_time),
        "metadata": {
            "ai_model": "GigaChat",
            "has_time": has_time,
            "was_date_parsed": was_date_parsed,
            "confidence_score": None
        }
    }

    return True, processed_task, warnings


def extract_task_via_gigachat(user_text: str) -> dict:
    base_response = {
        "success": False,
        "original_text": user_text,
        "processed_task": None,
        "warnings": []
    }

    token = get_token()
    if not token:
        base_response["error"] = "ИИ помощник не настроен"
        return base_response

    try:
        prompt = _build_gigachat_prompt(user_text)
        r = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "GigaChat",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_text}
                ],
                "temperature": 0.3,
                "max_tokens": 300
            },
            verify=False,
            timeout=20
        )

        if r.status_code != 200:
            base_response["error"] = f"Ошибка API GigaChat (код {r.status_code})"
            return base_response

        response_data = r.json()
        if "choices" not in response_data or not response_data["choices"]:
            base_response["error"] = "Ошибка формата ответа GigaChat"
            return base_response

        raw_content = response_data["choices"][0]["message"].get("content", "")
        parsed_json = _safe_json_loads(raw_content)
        ok, processed_task, warnings = _validate_and_enrich(parsed_json, user_text)

        base_response["success"] = ok
        base_response["processed_task"] = processed_task
        base_response["warnings"] = warnings

        if not ok:
            base_response["error"] = "Не удалось разобрать ответ модели"

        return base_response
    except Exception as exc:
        base_response["error"] = f"Ошибка соединения с GigaChat: {exc}"
        return base_response

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

    structured = extract_task_via_gigachat(message)
    if structured.get("success"):
        processed = structured["processed_task"] or {}
        date_part = processed.get("date")
        time_part = processed.get("time") or "время не указано"
        title = processed.get("title", "Задача")
        summary = f"Готово! '{title}' на {date_part} {time_part}. Категория: {processed.get('category')}. Приоритет: {processed.get('priority')}"
        if structured.get("warnings"):
            summary += "\nПредупреждения: " + "; ".join(structured["warnings"])
        return {
            'type': 'structured_task',
            'content': summary,
            'structured': structured
        }

    error_msg = structured.get("error") or "Не удалось обработать запрос"
    return {
        'type': 'text',
        'content': error_msg,
        'structured': structured
    }
