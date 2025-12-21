import json
import os
import re
import uuid
import ast
import hashlib
from datetime import datetime, timedelta, time as dtime
from typing import Literal, Optional, Dict, Any, List
import time

import requests
import certifi
import urllib3
from dotenv import load_dotenv

load_dotenv()

AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")
ACCESS_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

TOKEN_CACHE = None

# Дефолтная длительность события в минутах (если end_time отсутствует)
DEFAULT_EVENT_DURATION_MIN = 60

CATEGORIES = ["Работа", "Учеба", "Личное", "Здоровье", "Покупки", "Встречи"]
PRIORITIES = {"high", "medium", "low"}

# Ключевые слова для автоматического определения категорий
CATEGORY_KEYWORDS = {
    "Работа": [
        "работа", "проект", "встреча", "совещание", "бизнес", "офис", "коллеги", "начальник",
        "отчет", "презентация", "дедлайн", "задача", "клиент", "контракт", "переговоры",
    ],
    "Учеба": [
        "учеба", "урок", "экзамен", "лекция", "домашнее задание", "контрольная", "семинар",
        "курс", "обучение", "школа", "университет", "студент", "преподаватель", "учитель",
        "занятие", "пары",
    ],
    "Здоровье": [
        "врач", "больница", "аптека", "здоровье", "мед", "прием", "осмотр", "анализ",
        "спорт", "тренировка", "бег", "фитнес", "зал", "массаж", "стоматолог", "терапевт",
        "поликлиника",
    ],
    "Покупки": [
        "купить", "магазин", "покупки", "шопинг", "товары", "продукты", "супермаркет",
        "аптека", "одежда", "еда", "заказать", "доставка",
    ],
    "Встречи": [
        "встреча", "друг", "друзья", "семья", "родители", "дети", "поход", "кафе",
        "кино", "театр", "концерт", "праздник", "день рождения", "свидание",
    ],
    "Личное": [
        "личное", "дом", "быт", "уборка", "стирка", "ремонт", "счета", "платежи",
        "документы", "паспорт", "банк", "почта", "звонок",
    ],
}

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


def clean_event_title(title: str) -> str:
    """
    Очищает заголовок события от командных слов и служебных кусков.
    Удаляет: ведущие глаголы/команды, даты, время, нормализует пробелы.
    """
    if not title:
        return "Событие"
    
    text = title.strip()
    
    # Удаляем ведущие глаголы/команды (с формами)
    command_patterns = [
        r'^(поставь|поставить|добавь|добавить|создай|создать|запланируй|запланировать|назначь|назначить|напомни|напомнить|сделай|сделать)\s+',
        r'^(поставь|поставить|добавь|добавить|создай|создать|запланируй|запланировать|назначь|назначить|напомни|напомнить|сделай|сделать)',
    ]
    for pattern in command_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Удаляем ведущие "на завтра/завтра/сегодня/послезавтра"
    date_prefixes = [
        r'^(на\s+)?завтра\s+',
        r'^(на\s+)?сегодня\s+',
        r'^(на\s+)?послезавтра\s+',
        r'^завтра\s+',
        r'^сегодня\s+',
        r'^послезавтра\s+',
    ]
    for pattern in date_prefixes:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Удаляем упоминание времени вида "в 19:00" или просто "19:00"
    text = re.sub(r'\s*в\s+\d{1,2}[:\.]\d{2}\s*', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\d{1,2}[:\.]\d{2}\s*', ' ', text)
    
    # Нормализуем пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Делаем первую букву заглавной
    if text:
        text = text[0].upper() + text[1:]
    
    # Если результат пустой -> "Событие"
    if not text:
        return "Событие"
    
    # Специальные правила для прогулок
    text_lower = text.lower()
    if any(word in text_lower for word in ['гулять', 'прогуляться', 'прогулка']):
        return "Прогулка"
    
    return text


# Попробуем импортировать локальный парсер в разных контекстах (пакет или модуль)
try:
    from backend.ai_parser import local_parse as local_ai_parse
except Exception:
    try:
        from ai_parser import local_parse as local_ai_parse
    except Exception:
        local_ai_parse = None


def safe_json_extract(raw: str) -> Optional[dict]:
    """
    Улучшенная функция извлечения JSON из сырого ответа модели.
    Убирает ```json ``` обёртки, находит первый сбалансированный {...} и парсит его.
    """
    if isinstance(raw, dict):
        return raw

    if not isinstance(raw, str):
        return None

    # Убираем ```json ``` обёртки
    candidates = [raw]
    cleaned = re.sub(r'```json\s*', '', raw, flags=re.IGNORECASE)
    cleaned = re.sub(r'```\s*', '', cleaned)
    if cleaned.strip() != raw.strip():
        candidates.append(cleaned.strip())

    decoder = json.JSONDecoder()

    def _extract_by_braces(s: str) -> Optional[str]:
        """Находит первый сбалансированный {...} в строке."""
        start = s.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(s)):
            if s[i] == '{':
                depth += 1
            elif s[i] == '}':
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        return None

    for candidate in candidates:
        # Первый проход: стандартный json.loads
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Второй проход: попытка raw_decode от первого символа '{'
        brace_index = candidate.find("{")
        while brace_index != -1:
            try:
                obj, _ = decoder.raw_decode(candidate[brace_index:])
                return obj
            except json.JSONDecodeError:
                brace_index = candidate.find("{", brace_index + 1)

        # Третий проход: извлечь сбалансированный фрагмент по скобкам
        try:
            fragment = _extract_by_braces(candidate)
            if fragment:
                try:
                    return json.loads(fragment)
                except json.JSONDecodeError:
                    # Попробуем через ast.literal_eval (поддерживает одинарные кавычки)
                    try:
                        obj = ast.literal_eval(fragment)
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
        except Exception:
            pass

    return None


def _safe_json_loads(raw):
    """
    Пытается безопасно распарсить JSON из ответа модели,
    даже если вокруг есть пояснительный текст или обёртки.
    Использует улучшенную safe_json_extract.
    """
    return safe_json_extract(raw)


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


def detect_intent(text: str) -> Literal["availability", "create_event", "chat"]:
    """
    Определяет намерение пользователя: availability (узнать свободное время),
    create_event (создать событие) или chat (обычный чат).
    
    Правила:
    - availability: ключевые слова о свободном времени/окнах/занятости
    - create_event: явные глаголы создания + дата/время ИЛИ встреча/созвон + дата/время
    - chat: всё остальное
    """
    text_lower = text.lower().strip()
    
    # Ключевые слова для availability (свободное время)
    availability_keywords = [
        'свобод', 'свободен', 'свободна', 'свободно', 'свободное время',
        'окно', 'окна', 'слот', 'слоты', 'доступен', 'доступна', 'доступно',
        'занят', 'занята', 'занято', 'занятость',
        'когда я свободен', 'когда я свободна', 'когда свободен', 'когда свободна',
        'есть ли свободное время', 'есть свободное время',
        'найди свободное окно', 'найди свободные окна', 'назови все свободные окна',
        'когда я могу', 'могу ли я', 'есть ли у меня время',
        'когда у меня свободно', 'когда свободно', 'свободные промежутки'
    ]
    
    # Ключевые слова для create_event (создание события)
    # Обязательно явные глаголы намерения
    create_event_verbs = [
        'создай', 'создать', 'добавь', 'добавить', 'запланируй', 'запланировать',
        'поставь', 'поставить', 'назначь', 'назначить', 'забронируй', 'забронировать',
        'сделай встречу', 'сделать встречу', 'напомни', 'напомнить'
    ]
    
    # Сущности событий + дата/время (только если есть конкретная дата/время)
    event_nouns = ['встреча', 'созвон', 'звонок', 'митинг', 'совещание']
    date_time_patterns = [
        r'\d{1,2}[.\-]\d{1,2}',  # дд.мм или дд-мм
        r'\d{1,2}[:\.]\d{2}',    # HH:MM или HH.MM
        'сегодня', 'завтра', 'послезавтра', 'через день', 'через неделю'
    ]
    
    # Проверка availability (приоритет выше, чтобы не путать с create_event)
    has_availability = any(kw in text_lower for kw in availability_keywords)
    
    # Проверка create_event
    has_create_verb = any(verb in text_lower for verb in create_event_verbs)
    has_event_noun = any(noun in text_lower for noun in event_nouns)
    has_date_time = any(re.search(pattern, text_lower) for pattern in date_time_patterns)
    
    # create_event: явный глагол ИЛИ (сущность события + дата/время)
    is_create_event = has_create_verb or (has_event_noun and has_date_time)
    
    # Определение намерения
    if has_availability:
        return "availability"
    elif is_create_event:
        return "create_event"
    else:
        return "chat"


def is_task_request(message: str) -> bool:
    """
    УПРОЩЕННАЯ версия: определяет только create_event (не availability).
    Используется для обратной совместимости.
    """
    intent = detect_intent(message)
    return intent == "create_event"


def extract_task_via_gigachat(user_text: str, existing_tasks: list = None) -> dict:
    base_response = {
        "success": False,
        "original_text": user_text,
        "processed_task": None,
        "warnings": []
    }

    # Быстрый локальный фоллбек: сначала пытаемся локально распарсить задачу
    try:
        local_fallback_quick = None
        try:
            local_fallback_quick = local_ai_parse(user_text)
        except Exception:
            local_fallback_quick = None

        if local_fallback_quick:
            lf_date = local_fallback_quick.get('date')
            lf_time = local_fallback_quick.get('time')
            datetime_iso = None
            if lf_time and lf_date:
                datetime_iso = datetime.combine(lf_date, lf_time).isoformat()

            processed_task = {
                "title": _normalize_title(local_fallback_quick.get('description')),
                "description": f"Сгенерировано локальным парсером (instant) из заметки: '{user_text}'",
                "date": lf_date.isoformat() if lf_date else _today_with_weekday()[0].isoformat(),
                "time": lf_time.strftime("%H:%M") if lf_time else None,
                "datetime_iso": datetime_iso,
                "category": local_fallback_quick.get('category', 'Личное'),
                "priority": local_fallback_quick.get('priority', 'medium'),
                "is_full_day_event": not bool(lf_time),
                "metadata": {
                    "ai_model": "local_fallback_instant",
                    "has_time": bool(lf_time),
                    "was_date_parsed": True,
                    "confidence_score": None
                }
            }

            return {
                "success": True,
                "original_text": user_text,
                "processed_task": processed_task,
                "warnings": ["Использован локальный парсер (instant, без ожидания сети)"],
            }
    except Exception:
        # если локальный быстрый фоллбек упал, продолжаем обычный путь
        pass

    # Быстрый canned-ответ для коротких приветствий — не ждём сеть
    try:
        txt_low = (user_text or "").strip().lower()
        if len(txt_low) <= 20 and re.match(r'^(прив|здрав|алло|ало|hi|hello|hey)\b', txt_low):
            return {
                'success': True,
                'original_text': user_text,
                'processed_task': None,
                'warnings': [],
                'type': 'text',
                'content': 'Привет! Я Помняша, ИИ-ассистент для планирования. Пиши задачу — помогу распланировать.'
            }
    except Exception:
        pass

    def _log_parse_error(entry: dict):
        try:
            import json as _json
            log_path = os.path.join(os.path.dirname(__file__), 'ai_parse_errors.log')
            with open(log_path, 'a', encoding='utf-8') as fh:
                fh.write(_json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception:
            pass

    # Обновим переменные окружения и ключ перед запросом токена —
    # .env находится в `backend/.env`, поэтому явно подгружаем его.
    try:
        load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
    except Exception:
        # fallback: обычный load_dotenv
        try:
            load_dotenv()
        except Exception:
            pass

    global AUTHORIZATION_KEY
    AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")
    global TOKEN_CACHE
    TOKEN_CACHE = None

    token = get_token()
    if not token:
        base_response["error"] = "ИИ помощник не настроен"
        return base_response

    try:
        # Построим prompt: сначала пробуем внешний билдер (backend.ai_prompt),
        # который поддерживает передачу `existing_tasks`.
        prompt = None
        try:
            try:
                from backend.ai_prompt import build_gigachat_prompt
            except Exception:
                from ai_prompt import build_gigachat_prompt
            prompt = build_gigachat_prompt(user_text, existing_tasks=existing_tasks)
        except Exception:
            # fallback: локальный билдер внутри этого модуля
            try:
                prompt = _build_gigachat_prompt(user_text)
                if existing_tasks:
                    prompt += "\n\nExisting tasks:\n" + str(existing_tasks)
            except Exception:
                prompt = _build_gigachat_prompt(user_text)
        def _safe_post(url, **kwargs):
            kw = kwargs.copy()
            if 'verify' not in kw:
                kw['verify'] = certifi.where()
            try:
                return requests.post(url, **kw)
            except requests.exceptions.SSLError:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                kw['verify'] = False
                return requests.post(url, **kw)

        start = time.time()
        r = _safe_post(
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
            timeout=(3, 8)
        )
        elapsed = time.time() - start
        if elapsed > 5:
            try:
                import logging
                logging.getLogger(__name__).warning('Slow GigaChat request: %.2fs', elapsed)
            except Exception:
                pass

        # Логируем медленные ответы в файл для последующего анализа
        try:
            if elapsed > 1.0:
                snippet = None
                try:
                    snippet = r.text[:1000]
                except Exception:
                    snippet = None
                try:
                    _log_parse_error({
                        'timestamp': datetime.utcnow().isoformat(),
                        'type': 'slow_request',
                        'original_text': user_text,
                        'elapsed_s': round(elapsed, 3),
                        'status_code': getattr(r, 'status_code', None),
                        'response_snippet': snippet
                    })
                except Exception:
                    pass
        except Exception:
            pass

        if r.status_code != 200:
            base_response["error"] = f"Ошибка API GigaChat (код {r.status_code})"
            return base_response

        response_data = r.json()
        if "choices" not in response_data or not response_data["choices"]:
            base_response["error"] = "Ошибка формата ответа GigaChat"
            return base_response

        raw_content = response_data["choices"][0]["message"].get("content", "")
        parsed_json = safe_json_extract(raw_content)

        # Если модель явно указала, что это не задача — короткий путь для текстового ответа
        try:
            if isinstance(parsed_json, dict) and parsed_json.get('not_task'):
                return {
                    'success': True,
                    'original_text': user_text,
                    'processed_task': None,
                    'type': 'text',
                    'content': parsed_json.get('message') or 'Не задача'
                }
        except Exception:
            pass

        # Если парсинг не удался — попытаемся быстро "починить" ответ модели
        if parsed_json is None and raw_content:
            try:
                try:
                    from backend.ai_client import post_custom
                except Exception:
                    try:
                        from ai_client import post_custom
                    except Exception:
                        post_custom = None

                if post_custom:
                    repair_system = (
                        "Ты — ассистент-репаратор. Тебе дан сырой текст, сгенерированный другой моделью."
                        " Исправь формат и верни ТОЛЬКО корректный JSON в соответствии со схемой:"
                        " {\"title\": string, \"date\": string|null, \"time\": string|null,"
                        " \"duration_minutes\": integer|null, \"priority\": string|null, \"category\": string|null}."
                        " НИКАКОГО пояснительного текста, только JSON."
                    )
                    repair_user = (
                        "Ниже — сырой ответ модели. Исправь любые форматные ошибки и верни только JSON."
                        f"\n\nСырой ответ:\n{raw_content[:500]}"
                    )
                    repair = post_custom(system_prompt=repair_system, user_text=repair_user, max_attempts=1, timeout=6)
                    if repair and repair.get('success') and repair.get('raw'):
                        repaired_raw = repair.get('raw')
                        parsed_json = safe_json_extract(repaired_raw)
                        if parsed_json is not None:
                            raw_content = repaired_raw
            except Exception:
                parsed_json = None

        ok, processed_task, warnings = _validate_and_enrich(parsed_json, user_text)

        # Если модель вернула невалидный JSON или валидация не прошла,
        # сначала попробуем локальный парсер, затем — обычный чат-ответ.
        if not ok:
            local_fallback = None
            try:
                local_fallback = local_ai_parse(user_text)
            except Exception:
                local_fallback = None

            if local_fallback:
                # Построим обработанную задачу на основе локального парсера
                lf_date = local_fallback.get('date')
                lf_time = local_fallback.get('time')
                datetime_iso = None
                if lf_time:
                    datetime_iso = datetime.combine(lf_date, lf_time).isoformat()

                processed_task = {
                    "title": _normalize_title(local_fallback.get('description')),
                    "description": f"Сгенерировано локальным парсером из заметки: '{user_text}'",
                    "date": lf_date.isoformat() if lf_date else _today_with_weekday()[0].isoformat(),
                    "time": lf_time.strftime("%H:%M") if lf_time else None,
                    "datetime_iso": datetime_iso,
                    "category": local_fallback.get('category', 'Личное'),
                    "priority": local_fallback.get('priority', 'medium'),
                    "is_full_day_event": not bool(lf_time),
                    "metadata": {
                        "ai_model": "local_fallback",
                        "has_time": bool(lf_time),
                        "was_date_parsed": True,
                        "confidence_score": None
                    }
                }

                warnings.append("Использован локальный парсер (fallback)")
                ok = True
                base_response["raw_model"] = raw_content
                try:
                    _log_parse_error({
                        'timestamp': datetime.utcnow().isoformat(),
                        'type': 'local_fallback_used',
                        'original_text': user_text,
                        'raw_model': raw_content,
                        'note': 'local parser used because model JSON invalid'
                    })
                except Exception:
                    pass
            else:
                # Если локальный парсер не нашёл задачу — вернёмся к обычному чат-режиму
                try:
                    # Импортируем клиент устойчиво: сначала пробуем пакет, затем модуль
                    try:
                        from backend.ai_client import post_conversation
                    except Exception:
                        from ai_client import post_conversation

                    conv = post_conversation(user_text)
                    if conv.get('success') and conv.get('raw'):
                        # Возвращаем текстовый ответ модели (чат-режим)
                        return {
                            'success': True,
                            'original_text': user_text,
                            'processed_task': None,
                            'warnings': [],
                            'type': 'text',
                            'content': conv.get('raw')
                        }
                    else:
                        base_response["raw_model"] = raw_content
                        try:
                            _log_parse_error({
                                'timestamp': datetime.utcnow().isoformat(),
                                'type': 'conversation_fallback_failed',
                                'original_text': user_text,
                                'raw_model': raw_content,
                                'note': 'conversation fallback did not return text'
                            })
                        except Exception:
                            pass
                except Exception:
                    base_response["raw_model"] = raw_content
                    try:
                        _log_parse_error({
                            'timestamp': datetime.utcnow().isoformat(),
                            'type': 'conversation_fallback_error',
                            'original_text': user_text,
                            'raw_model': raw_content,
                            'note': 'exception while doing conversation fallback'
                        })
                    except Exception:
                        pass

        base_response["success"] = ok
        base_response["processed_task"] = processed_task
        base_response["warnings"] = warnings

        if not ok:
            # Сохраняем сырой ответ модели для отладки парсинга
            base_response["raw_model"] = raw_content
            try:
                _log_parse_error({
                    'timestamp': datetime.utcnow().isoformat(),
                    'type': 'parse_failed',
                    'original_text': user_text,
                    'raw_model': raw_content,
                    'warnings': warnings
                })
            except Exception:
                pass

            # Возвращаем дружелюбное сообщение вместо технической ошибки
            return {
                'success': True,
                'original_text': user_text,
                'processed_task': None,
                'warnings': warnings,
                'type': 'text',
                'content': 'Не смог распознать задачу. Можете переформулировать или дать дополнительные подробности?'
            }

        return base_response
    except requests.exceptions.RequestException as exc:
        base_response["error"] = f"Ошибка соединения с GigaChat: {exc}"
        return base_response
    except Exception as exc:
        base_response["error"] = f"Ошибка при обработке запроса: {exc}"
        return base_response

def parse_availability_constraints(text: str) -> Dict[str, Any]:
    """
    Парсит ограничения времени из запроса о доступности.
    Возвращает словарь с полями:
    - duration_minutes: длительность слота (по умолчанию 30)
    - date: конкретная дата или None
    - date_range: (start_date, end_date) для диапазона или None
    - time_window: (start_time, end_time) или None
    - after_time: время "после" или None
    - before_time: время "до" или None
    """
    text_lower = text.lower()
    constraints = {
        'duration_minutes': 30,  # дефолт
        'date': None,
        'date_range': None,
        'time_window': None,
        'after_time': None,
        'before_time': None
    }
    
    # Парсинг длительности
    duration_patterns = [
        (r'на\s+(\d+)\s+минут', lambda m: int(m.group(1))),
        (r'(\d+)\s+минут', lambda m: int(m.group(1))),
        (r'полчаса|30\s+минут', lambda m: 30),
        (r'на\s+час|1\s+час|60\s+минут', lambda m: 60),
        (r'на\s+(\d+)\s+часов?', lambda m: int(m.group(1)) * 60),
        (r'(\d+)\s+часов?', lambda m: int(m.group(1)) * 60),
    ]
    for pattern, converter in duration_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                constraints['duration_minutes'] = converter(match)
                break
            except:
                pass
    
    # Парсинг даты
    today = datetime.now().date()
    date_patterns = {
        'сегодня': today,
        'завтра': today + timedelta(days=1),
        'послезавтра': today + timedelta(days=2),
    }
    
    for pattern, target_date in date_patterns.items():
        if pattern in text_lower:
            constraints['date'] = target_date
            break
    
    # Парсинг "на этой неделе"
    if 'на этой неделе' in text_lower or 'на неделе' in text_lower:
        # От понедельника до воскресенья текущей недели
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)
        week_end = week_start + timedelta(days=6)
        constraints['date_range'] = (week_start, week_end)
    
    # Парсинг числовых дат (дд.мм или дд-мм)
    date_match = re.search(r'(\d{1,2})[.\-](\d{1,2})(?:[.\-](\d{2,4}))?', text)
    if date_match and not constraints['date']:
        day, month = int(date_match.group(1)), int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            constraints['date'] = datetime(year, month, day).date()
        except ValueError:
            pass
    
    # Парсинг временных окон
    time_windows = {
        'утром': (dtime(9, 0), dtime(12, 0)),
        'днем': (dtime(12, 0), dtime(17, 0)),
        'вечером': (dtime(17, 0), dtime(21, 0)),
        'ночью': (dtime(21, 0), dtime(9, 0)),  # особый случай
    }
    
    for keyword, (start_t, end_t) in time_windows.items():
        if keyword in text_lower:
            constraints['time_window'] = (start_t, end_t)
            break
    
    # Парсинг "после HH:MM" или "после HH"
    after_match = re.search(r'после\s+(\d{1,2})(?:[:\.](\d{2}))?', text_lower)
    if after_match:
        hour = int(after_match.group(1))
        minute = int(after_match.group(2)) if after_match.group(2) else 0
        try:
            constraints['after_time'] = dtime(hour, minute)
        except ValueError:
            pass
    
    # Парсинг "до HH:MM" или "до HH"
    before_match = re.search(r'до\s+(\d{1,2})(?:[:\.](\d{2}))?', text_lower)
    if before_match:
        hour = int(before_match.group(1))
        minute = int(before_match.group(2)) if before_match.group(2) else 0
        try:
            constraints['before_time'] = dtime(hour, minute)
        except ValueError:
            pass
    
    return constraints


def generate_idempotency_key(user_id: int, title: str, date: str, start: str, duration_min: int) -> str:
    """
    Генерирует idempotency_key для предотвращения дублей событий.
    
    Args:
        user_id: ID пользователя
        title: название события
        date: дата в формате YYYY-MM-DD
        start: время начала в формате HH:MM
        duration_min: длительность в минутах
    
    Returns:
        SHA256 хеш строки
    """
    key_string = f"{user_id}|{title}|{date}|{start}|{duration_min}"
    return hashlib.sha256(key_string.encode('utf-8')).hexdigest()


def has_conflict(start_dt: datetime, end_dt: datetime, existing_events: List) -> bool:
    """
    Проверяет конфликт между новым событием (start_dt, end_dt) и существующими событиями.
    
    Args:
        start_dt: начало нового события
        end_dt: конец нового события
        existing_events: список существующих событий (с полями start_time, end_time или duration_min)
    
    Returns:
        True если есть конфликт (пересечение интервалов)
    """
    for event in existing_events:
        event_start = event.start_time
        # Если end_time отсутствует, используем дефолтную длительность
        if event.end_time:
            event_end = event.end_time
        else:
            # Используем duration_min если есть, иначе DEFAULT_EVENT_DURATION_MIN
            duration_min = getattr(event, 'duration_min', None) or DEFAULT_EVENT_DURATION_MIN
            event_end = event_start + timedelta(minutes=duration_min)
        
        # Конфликт если интервалы пересекаются
        # start < existing_end AND end > existing_start
        if start_dt < event_end and end_dt > event_start:
            return True
    
    return False


def get_free_slots_for_date(date, existing_events, min_duration_minutes: int = 30, 
                            work_start: dtime = dtime(9, 0), work_end: dtime = dtime(18, 0),
                            after_time: Optional[dtime] = None, before_time: Optional[dtime] = None):
    """
    Находит свободные временные слоты на заданную дату.
    
    Args:
        date: дата для поиска слотов
        existing_events: список существующих событий
        min_duration_minutes: минимальная длительность слота (по умолчанию 30)
        work_start: начало рабочего дня (по умолчанию 09:00)
        work_end: конец рабочего дня (по умолчанию 18:00)
        after_time: не возвращать слоты до этого времени
        before_time: не возвращать слоты после этого времени
    
    Returns:
        Список словарей с полями: start, end, duration_minutes
    """
    # Применяем ограничения времени
    # ВАЖНО: если after_time > 18:00, расширяем рабочие часы до 23:59
    effective_start = work_start
    effective_end = work_end
    
    if after_time:
        effective_start = max(effective_start, after_time)
        # Если after_time > 18:00, расширяем рабочие часы
        if after_time > work_end:
            effective_end = dtime(23, 59)
    if before_time:
        effective_end = min(effective_end, before_time)
    
    work_start_dt = datetime.combine(date, effective_start)
    work_end_dt = datetime.combine(date, effective_end)
    
    # Если after_time > before_time, нет доступных слотов
    if effective_start >= effective_end:
        return []

    # Сортируем существующие события по времени
    sorted_events = sorted(existing_events, key=lambda x: x.start_time)

    free_slots = []
    current_time = work_start_dt

    for event in sorted_events:
        event_start = event.start_time
        # Если end_time не указан, используем duration_min или DEFAULT_EVENT_DURATION_MIN
        if event.end_time:
            event_end = event.end_time
        else:
            duration_min = getattr(event, 'duration_min', None) or DEFAULT_EVENT_DURATION_MIN
            event_end = event_start + timedelta(minutes=duration_min)

        # Если событие начинается после текущего времени, добавляем свободный слот
        if event_start > current_time:
            slot_duration_minutes = (event_start - current_time).total_seconds() / 60
            if slot_duration_minutes >= min_duration_minutes:
                free_slots.append({
                    'start': current_time,
                    'end': event_start,
                    'duration_minutes': int(slot_duration_minutes)
                })

        # Обновляем текущее время на конец события
        current_time = max(current_time, event_end)

    # Добавляем слот после последнего события до конца рабочего дня
    if current_time < work_end_dt:
        slot_duration_minutes = (work_end_dt - current_time).total_seconds() / 60
        if slot_duration_minutes >= min_duration_minutes:
            free_slots.append({
                'start': current_time,
                'end': work_end_dt,
                'duration_minutes': int(slot_duration_minutes)
            })

    return free_slots

def auto_assign_category(title: str, description: str = "") -> str:
    """
    Автоматически определяет категорию задачи на основе её названия и описания.
    Возвращает наиболее подходящую категорию из списка CATEGORIES.
    """
    text = f"{title} {description}".lower().strip()

    if not text:
        return "Личное"

    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            kw = keyword.lower()
            if not kw:
                continue
            # количество вхождений + бонус за отдельные слова
            score += text.count(kw)
            if f" {kw} " in f" {text} ":
                score += 2
        scores[category] = score

    best_category, best_score = max(scores.items(), key=lambda x: x[1])
    if best_score <= 0:
        return "Личное"
    return best_category


def handle_availability_request(text: str, db_session, user_id: int) -> Dict[str, Any]:
    """
    Обрабатывает запрос о свободном времени (availability).
    ВАЖНО: НЕ создаёт события, только показывает доступность.
    
    Returns:
        dict с полями (строгий контракт):
        - type: "availability_result"
        - message: человекочитаемый текст ответа
        - slots: список слотов [{"date": "YYYY-MM-DD", "start": "HH:MM", "end": "HH:MM"}]
        - hint_command: подсказка-команда для создания события (если есть слоты)
        - constraints: информация об ограничениях
        - reason: объяснение если слотов нет (null если есть)
    """
    from backend.database import Event
    
    text_lower = text.lower()
    
    # Определяем режим: point (ближайшее окно) или range (когда свободен)
    range_keywords = ['когда я свободен', 'когда свободен', 'в какое время свободен', 
                      'когда у меня свободно', 'когда свободно']
    availability_mode = "range" if any(kw in text_lower for kw in range_keywords) else "point"
    
    constraints = parse_availability_constraints(text)
    duration_minutes = constraints['duration_minutes']
    
    # Определяем диапазон дат для поиска
    target_dates = []
    if constraints['date']:
        target_dates = [constraints['date']]
    elif constraints['date_range']:
        start_date, end_date = constraints['date_range']
        current = start_date
        while current <= end_date:
            target_dates.append(current)
            current += timedelta(days=1)
    else:
        # По умолчанию - сегодня
        target_dates = [datetime.now().date()]
    
    # Собираем все события для целевых дат
    all_raw_slots = []
    for target_date in target_dates:
        existing_events = db_session.query(Event).filter(
            Event.user_id == user_id,
            Event.start_time >= datetime.combine(target_date, datetime.min.time()),
            Event.start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
        ).all()
        
        # Получаем свободные слоты с учетом ограничений
        slots = get_free_slots_for_date(
            target_date,
            existing_events,
            min_duration_minutes=duration_minutes,
            after_time=constraints['after_time'],
            before_time=constraints['before_time']
        )
        
        # Фильтруем по time_window если указан
        if constraints['time_window']:
            start_t, end_t = constraints['time_window']
            filtered_slots = []
            for slot in slots:
                slot_start_time = slot['start'].time()
                # Особый случай для "ночью" (21:00-09:00)
                if start_t > end_t:  # ночь
                    if slot_start_time >= start_t or slot_start_time < end_t:
                        filtered_slots.append(slot)
                else:
                    if start_t <= slot_start_time < end_t:
                        filtered_slots.append(slot)
            slots = filtered_slots
        
        all_raw_slots.extend(slots)
    
    # НОРМАЛИЗАЦИЯ: обрезаем слоты до запрошенной длительности
    # Даже если свободно 9 часов, показываем только нужную длительность
    normalized_slots = []
    for slot in all_raw_slots:
        if slot['duration_minutes'] >= duration_minutes:
            # Обрезаем слот до запрошенной длительности
            slot_start = slot['start']
            slot_end = slot_start + timedelta(minutes=duration_minutes)
            normalized_slots.append({
                'start': slot_start,
                'end': slot_end,
                'duration_minutes': duration_minutes,
                'date': slot_start.date()
            })
    
    # Формируем ответ если слотов нет
    if not normalized_slots:
        reason_parts = []
        if constraints['after_time']:
            time_str = constraints['after_time'].strftime('%H:%M')
            reason_parts.append(f"после {time_str}")
        if constraints['before_time']:
            time_str = constraints['before_time'].strftime('%H:%M')
            reason_parts.append(f"до {time_str}")
        if constraints['time_window']:
            start_t, end_t = constraints['time_window']
            if start_t > end_t:  # ночь
                reason_parts.append("ночью")
            elif start_t == dtime(9, 0) and end_t == dtime(12, 0):
                reason_parts.append("утром")
            elif start_t == dtime(12, 0) and end_t == dtime(17, 0):
                reason_parts.append("днём")
            elif start_t == dtime(17, 0) and end_t == dtime(21, 0):
                reason_parts.append("вечером")
        
        reason_text = f" {' '.join(reason_parts)}" if reason_parts else ""
        date_text = ""
        if constraints['date']:
            date_obj = constraints['date']
            if date_obj == datetime.now().date():
                date_text = "сегодня"
            elif date_obj == datetime.now().date() + timedelta(days=1):
                date_text = "завтра"
            else:
                date_text = date_obj.strftime('%d.%m.%Y')
        
        text_response = f"К сожалению,{reason_text} нет свободных интервалов длительностью ≥ {duration_minutes} минут."
        if date_text:
            text_response = f"К сожалению, {date_text}{reason_text} нет свободных интервалов длительностью ≥ {duration_minutes} минут."
        text_response += f"\nПопробуйте уменьшить длительность или выбрать другую дату."
        
        # Формируем constraints для ответа
        constraints_dict = {
            "duration_min": duration_minutes
        }
        if constraints['date']:
            date_str = constraints['date'].isoformat()
            constraints_dict["date_range"] = {"start": date_str, "end": date_str}
        elif constraints['date_range']:
            start_date, end_date = constraints['date_range']
            constraints_dict["date_range"] = {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        if constraints['time_window']:
            start_t, end_t = constraints['time_window']
            constraints_dict["time_window"] = {
                "start": start_t.strftime('%H:%M'),
                "end": end_t.strftime('%H:%M')
            }
        
        return {
            'type': 'availability_result',
            'message': text_response,
            'slots': [],
            'hint_command': None,
            'constraints': constraints_dict,
            'reason': f"Нет свободных интервалов ≥ {duration_minutes} минут{reason_text}"
        }
    
    # Сортируем слоты по времени начала
    normalized_slots.sort(key=lambda x: x['start'])
    
    # Ограничиваем количество слотов
    wants_all = 'все' in text_lower or 'назови все' in text_lower or 'все окна' in text_lower
    max_slots = len(normalized_slots) if wants_all else min(3, len(normalized_slots))
    selected_slots = normalized_slots[:max_slots]
    
    # Формируем текстовый ответ в зависимости от режима
    if availability_mode == "range":
        # Режим "когда я свободен" - показываем диапазоны
        text_response = _format_range_response(selected_slots, constraints, duration_minutes)
    else:
        # Режим "ближайшее окно" - показываем конкретные слоты
        text_response = _format_point_response(selected_slots, constraints, duration_minutes)
    
    # Преобразуем слоты в формат для фронта согласно контракту
    slots_for_frontend = []
    for slot in selected_slots:
        slots_for_frontend.append({
            'date': slot['date'].isoformat(),
            'start': slot['start'].strftime('%H:%M'),
            'end': slot['end'].strftime('%H:%M')
        })
    
    # Генерируем hint_command по первому слоту (вариант 2)
    hint_command = None
    if selected_slots:
        first_slot = selected_slots[0]
        date_str = first_slot['date'].strftime('%d.%m.%Y')
        start_str = first_slot['start'].strftime('%H:%M')
        hint_command = f"Если хочешь поставить встречу в это время, напиши: «Создай встречу {date_str} в {start_str} на {duration_minutes} минут»"
    
    # Формируем constraints для ответа
    constraints_dict = {
        "duration_min": duration_minutes
    }
    if constraints['date']:
        date_str = constraints['date'].isoformat()
        constraints_dict["date_range"] = {"start": date_str, "end": date_str}
    elif constraints['date_range']:
        start_date, end_date = constraints['date_range']
        constraints_dict["date_range"] = {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        }
    if constraints['time_window']:
        start_t, end_t = constraints['time_window']
        constraints_dict["time_window"] = {
            "start": start_t.strftime('%H:%M'),
            "end": end_t.strftime('%H:%M')
        }
    
    return {
        'type': 'availability_result',
        'message': text_response,
        'slots': slots_for_frontend,
        'hint_command': hint_command,
        'constraints': constraints_dict,
        'reason': None
    }


def _format_range_response(slots: List[Dict], constraints: Dict, duration_minutes: int) -> str:
    """Форматирует ответ для режима 'range' (когда я свободен)"""
    if not slots:
        return ""
    
    # Группируем слоты по датам
    slots_by_date = {}
    for slot in slots:
        date_key = slot['date']
        if date_key not in slots_by_date:
            slots_by_date[date_key] = []
        slots_by_date[date_key].append(slot)
    
    # Форматируем дату
    def format_date(date_obj):
        today = datetime.now().date()
        if date_obj == today:
            return "сегодня"
        elif date_obj == today + timedelta(days=1):
            return "завтра"
        else:
            return date_obj.strftime('%d.%m.%Y')
    
    # Форматируем время окна
    def format_time_window(slot):
        start_str = slot['start'].strftime('%H:%M')
        end_str = slot['end'].strftime('%H:%M')
        return f"{start_str}–{end_str}"
    
    parts = []
    for date_key in sorted(slots_by_date.keys()):
        date_slots = slots_by_date[date_key]
        date_text = format_date(date_key)
        
        # Определяем период дня если есть
        period_text = ""
        if constraints.get('time_window'):
            start_t, end_t = constraints['time_window']
            if start_t == dtime(9, 0) and end_t == dtime(12, 0):
                period_text = " утром"
            elif start_t == dtime(12, 0) and end_t == dtime(17, 0):
                period_text = " днём"
            elif start_t == dtime(17, 0) and end_t == dtime(21, 0):
                period_text = " вечером"
        
        if len(date_slots) == 1:
            # Одно окно
            slot = date_slots[0]
            time_window = format_time_window(slot)
            parts.append(f"{date_text}{period_text} ты свободен с {time_window}")
        else:
            # Несколько окон
            time_windows = [format_time_window(s) for s in date_slots]
            parts.append(f"{date_text}{period_text} ты свободен: {', '.join(time_windows)}")
    
    if len(parts) == 1:
        return parts[0] + "."
    else:
        return "Я нашёл свободные окна:\n" + "\n".join(f"• {p}" for p in parts)


def _format_point_response(slots: List[Dict], constraints: Dict, duration_minutes: int) -> str:
    """Форматирует ответ для режима 'point' (ближайшее окно)"""
    if not slots:
        return ""
    
    def format_date(date_obj):
        today = datetime.now().date()
        if date_obj == today:
            return "сегодня"
        elif date_obj == today + timedelta(days=1):
            return "завтра"
        else:
            return date_obj.strftime('%d.%m.%Y')
    
    def format_slot(slot):
        date_text = format_date(slot['date'])
        start_str = slot['start'].strftime('%H:%M')
        end_str = slot['end'].strftime('%H:%M')
        return f"{date_text} {start_str}–{end_str}"
    
    if len(slots) == 1:
        slot = slots[0]
        return f"Ближайшее свободное окно: {format_slot(slot)}."
    else:
        text = f"Я нашёл {len(slots)} свободных окна:\n"
        for i, slot in enumerate(slots, 1):
            text += f"• {format_slot(slot)}\n"
        return text.strip()


def suggest_optimal_time(date, description, existing_events, priority: str = "medium"):
    """
    Предлагает *конкретное время* начала события внутри свободных слотов.
    Не возвращает 09:00 по умолчанию, а подбирает час в пределах свободного окна.
    """
    return suggest_optimal_time_with_exclusions(date, description, existing_events, priority, [])


def suggest_optimal_time_with_exclusions(date, description, existing_events, priority: str = "medium", exclude_times: list = None):
    """
    Предлагает оптимальное время с учетом уже предложенных времен (exclude_times).
    Анализирует занятость более точно, учитывая длительность событий и перерывы между ними.
    """
    if exclude_times is None:
        exclude_times = []
    
    free_slots = get_free_slots_for_date(date, existing_events)
    if not free_slots:
        return None

    event_type = (description or "").lower()

    # Предпочитаемые часы для разных типов задач
    time_prefs_by_category = {
        "work": [9, 10, 11, 14, 15, 16],
        "lunch": [12, 13, 14],
        "sport": [7, 8, 18, 19, 20],
        "health": [9, 10, 11, 17, 18],
        "shopping": [11, 12, 17, 18, 19],
        "personal": [10, 11, 17, 18, 19],
    }

    # Определяем категорию для подбора времени
    if any(w in event_type for w in ["встреча", "совещание", "митинг", "meeting", "работа", "проект", "бизнес"]):
        category = "work"
    elif any(w in event_type for w in ["обед", "перерыв", "пауза", "кушать", "поесть"]):
        category = "lunch"
    elif any(w in event_type for w in ["спорт", "тренировка", "бег", "фитнес", "зал", "пробежка"]):
        category = "sport"
    elif any(w in event_type for w in ["врач", "больница", "аптека", "здоровье", "мед"]):
        category = "health"
    elif any(w in event_type for w in ["купить", "магазин", "покупки", "шопинг"]):
        category = "shopping"
    else:
        category = "personal"

    preferred_hours = time_prefs_by_category[category]

    # Преобразуем exclude_times в datetime для сравнения
    exclude_datetimes = []
    for time_str in exclude_times:
        try:
            if isinstance(time_str, str) and ':' in time_str:
                hour, minute = map(int, time_str.split(':'))
                exclude_datetimes.append(datetime.combine(date, datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()))
        except Exception:
            pass

    # Строим список всех допустимых кандидатов времени (datetime) внутри свободных слотов
    # Учитываем не только предпочтительные часы, но и все доступные времена с шагом 30 минут
    candidates = []
    
    # Сначала пробуем предпочтительные часы
    for slot in free_slots:
        start_hour = slot["start"].hour
        end_hour = slot["end"].hour
        for h in preferred_hours:
            if start_hour <= h < end_hour:
                candidate = datetime.combine(date, datetime.strptime(f"{h:02d}:00", "%H:%M").time())
                # Проверяем, что это время не в списке исключений
                if not any(abs((candidate - excl).total_seconds()) < 1800 for excl in exclude_datetimes):
                    candidates.append(candidate)
    
    # Если предпочтительные часы все исключены, генерируем варианты с шагом 30 минут
    if not candidates:
        for slot in free_slots:
            current = slot["start"]
            while current < slot["end"]:
                # Пропускаем исключенные времена
                if not any(abs((current - excl).total_seconds()) < 1800 for excl in exclude_datetimes):
                    candidates.append(current)
                current += timedelta(minutes=30)
                if len(candidates) >= 10:  # Ограничиваем количество кандидатов
                    break
            if len(candidates) >= 10:
                break

    # Если ничего не найдено, возвращаем None
    if not candidates:
        return None

    candidates.sort()

    # Выбираем оптимальное время в зависимости от приоритета
    if priority == "high":
        return candidates[0]
    if priority == "low":
        return candidates[-1]

    # Для среднего приоритета берём ближайшее к 15:00, но не из исключенных
    target = datetime.combine(date, datetime.strptime("15:00", "%H:%M").time())
    best = min(candidates, key=lambda dt: abs((dt - target).total_seconds()))
    return best


def get_token():
    global TOKEN_CACHE
    if TOKEN_CACHE:
        return TOKEN_CACHE

    if not AUTHORIZATION_KEY or AUTHORIZATION_KEY == "YOUR_GIGACHAT_AUTH_KEY_HERE":
        return None

    try:
        rquid = str(uuid.uuid4())
        try:
            r = requests.post(
                ACCESS_URL,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "RqUID": rquid,
                    "Authorization": f"Bearer {AUTHORIZATION_KEY}"
                },
                data={"scope": "GIGACHAT_API_PERS"},
                verify=certifi.where(),
                timeout=10
            )
        except requests.exceptions.SSLError:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
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
    Расширенная версия ask_gigachat с правильной обработкой intent'ов:
    - availability: запросы о свободном времени
    - create_event: создание события
    - chat: обычный чат
    """
    # Перезагружаем переменные окружения при каждом вызове
    load_dotenv()
    global AUTHORIZATION_KEY
    AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

    # Сбрасываем кэш токена при каждом вызове для надежности
    global TOKEN_CACHE
    TOKEN_CACHE = None

    # Определяем намерение пользователя
    intent = detect_intent(message)
    
    # Обработка availability-запросов
    if intent == "availability":
        if db_session and user_id:
            try:
                return handle_availability_request(message, db_session, user_id)
            except Exception as e:
                return {
                    'type': 'text',
                    'content': f'Ошибка при поиске свободного времени: {str(e)}'
                }
        else:
            return {
                'type': 'text',
                'content': 'Для поиска свободного времени требуется авторизация.'
            }
    
    # Обработка create_event-запросов
    if intent == "create_event":
        # Если есть сессия БД — передаём существующие таски в модель как контекст
        existing_tasks = None
        if db_session is not None and user_id is not None:
            try:
                from backend.database import Event
                evs = db_session.query(Event).filter(Event.user_id == user_id).all()
                existing_tasks = []
                for e in evs:
                    existing_tasks.append({
                        'id': e.id,
                        'title': e.title,
                        'start': e.start_time.isoformat() if e.start_time else None,
                        'end': e.end_time.isoformat() if e.end_time else None,
                        'source': e.source,
                        'external_id': e.external_id
                    })
            except Exception:
                existing_tasks = None
        
        # Используем extract_task_via_gigachat для создания события
        structured = extract_task_via_gigachat(message, existing_tasks=existing_tasks)

        # Если модель вернула удачно распознанную задачу — предложим пользователю подтверждение
        if structured.get("success"):
            processed = structured["processed_task"] or {}
            
            from backend.database import Event
            
            # Определяем параметры события
            raw_title = processed.get("title", "Событие")
            # Очищаем title от командных слов и служебных кусков
            title = clean_event_title(raw_title)
            date_str = processed.get('date')
            time_str = processed.get('time')
            category = processed.get('category', 'Личное')
            priority = processed.get('priority', 'medium')
            
            # Определяем длительность
            duration_min = DEFAULT_EVENT_DURATION_MIN
            if 'duration_minutes' in processed:
                duration_min = processed['duration_minutes']
            elif 'duration_min' in processed:
                duration_min = processed['duration_min']
            
            # Если дата не указана, используем сегодня
            if not date_str:
                date_obj = datetime.now().date()
            else:
                try:
                    date_obj = datetime.fromisoformat(date_str).date()
                except:
                    date_obj = datetime.now().date()
            
            # Получаем существующие события на эту дату для проверки конфликтов
            existing_events = []
            if db_session and user_id:
                existing_events = db_session.query(Event).filter(
                    Event.user_id == user_id,
                    Event.start_time >= datetime.combine(date_obj, datetime.min.time()),
                    Event.start_time < datetime.combine(date_obj + timedelta(days=1), datetime.min.time())
                ).all()
            
            # Определяем время начала
            suggested_time_dt = None
            if time_str:
                try:
                    hour, minute = map(int, time_str.split(':'))
                    suggested_time_dt = datetime.combine(date_obj, dtime(hour, minute))
                except:
                    pass
            
            # Если время не указано, предлагаем оптимальное
            if not suggested_time_dt:
                suggested = suggest_optimal_time(date_obj, title, existing_events, priority)
                if suggested:
                    suggested_time_dt = suggested
                else:
                    # Если нет свободного времени, возвращаем альтернативы
                    return {
                        'type': 'text',
                        'content': f'На {date_obj.strftime("%d.%m.%Y")} нет свободного времени для события "{title}". Попробуйте выбрать другую дату.'
                    }
            
            # Проверяем конфликт перед предложением
            end_time_dt = suggested_time_dt + timedelta(minutes=duration_min)
            if has_conflict(suggested_time_dt, end_time_dt, existing_events):
                # Конфликт обнаружен - предлагаем альтернативы
                alternative = suggest_optimal_time_with_exclusions(
                    date_obj, title, existing_events, priority, 
                    exclude_times=[suggested_time_dt.strftime('%H:%M')]
                )
                if alternative:
                    alternative_str = alternative.strftime('%H:%M')
                    return {
                        'type': 'text',
                        'content': f'Время {suggested_time_dt.strftime("%H:%M")} занято. Предлагаю альтернативу: {alternative_str}'
                    }
                else:
                    return {
                        'type': 'text',
                        'content': f'Время {suggested_time_dt.strftime("%H:%M")} занято, и нет других свободных окон на эту дату.'
                    }
            
            # Генерируем idempotency_key
            idempotency_key = generate_idempotency_key(
                user_id or 0,
                title,
                date_obj.isoformat(),
                suggested_time_dt.strftime('%H:%M'),
                duration_min
            )
            
            # Возвращаем event_suggestion согласно контракту
            return {
                'type': 'event_suggestion',
                'title': title,
                'date': date_obj.isoformat(),
                'start': suggested_time_dt.strftime('%H:%M'),
                'duration_min': duration_min,
                'category': category,
                'priority': priority,
                'actions': ['confirm', 'cancel', 'other_time'],
                'idempotency_key': idempotency_key
            }

        error_msg = structured.get("error") or "Не удалось обработать запрос"
        return {
            'type': 'text',
            'content': error_msg,
            'structured': structured
        }
    
    # Обработка chat-запросов (intent == "chat")
    try:
        # Импортируем клиент устойчиво: сначала пробуем пакет, затем модуль
        try:
            from backend.ai_client import post_conversation
        except Exception:
            from ai_client import post_conversation

        conv = post_conversation(message)
        if conv.get('success') and conv.get('raw'):
            # Возвращаем текстовый ответ модели (чат-режим)
            return {
                'success': True,
                'original_text': message,
                'processed_task': None,
                'warnings': [],
                'type': 'text',
                'content': conv.get('raw')
            }
        else:
            return {
                'success': True,
                'original_text': message,
                'processed_task': None,
                'warnings': [],
                'type': 'text',
                'content': 'Извините, я не смог обработать ваш запрос. Попробуйте переформулировать.'
            }
    except Exception as e:
        return {
            'success': True,
            'original_text': message,
            'processed_task': None,
            'warnings': [],
            'type': 'text',
            'content': 'Произошла ошибка при обработке сообщения.'
        }
