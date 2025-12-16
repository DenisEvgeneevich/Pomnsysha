import json
import os
import re
import uuid
import ast
from datetime import datetime, timedelta
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

CATEGORIES = ["Работа", "Учеба", "Личное", "Здоровье", "Покупки", "Встречи"]
PRIORITIES = {"high", "medium", "low"}

# Ключевые слова для автоматического определения категорий
CATEGORY_KEYWORDS = {
    "Работа": [
        "работа", "проект", "встреча", "совещание", "бизнес", "офис", "коллеги", "начальник",
        "отчет", "презентация", "дедлайн", "задача", "проект", "клиент", "контракт", "переговоры"
    ],
    "Учеба": [
        "учеба", "урок", "экзамен", "лекция", "домашнее задание", "контрольная", "семинар",
        "курс", "обучение", "школа", "университет", "студент", "преподаватель", "учитель"
    ],
    "Здоровье": [
        "врач", "больница", "аптека", "здоровье", "мед", "прием", "осмотр", "анализ",
        "спорт", "тренировка", "бег", "фитнес", "зал", "массаж", "стоматолог", "терапевт"
    ],
    "Покупки": [
        "купить", "магазин", "покупки", "шопинг", "товары", "продукты", "супермаркет",
        "аптека", "одежда", "еда", "заказать", "доставка"
    ],
    "Встречи": [
        "встреча", "друг", "друзья", "семья", "родители", "дети", "поход", "кафе",
        "кино", "театр", "концерт", "праздник", "день рождения", "свидание"
    ],
    "Личное": [
        "личное", "дом", "быт", "уборка", "стирка", "ремонт", "счета", "платежи",
        "документы", "паспорт", "банку", "почта", "звонок", "личный"
    ]
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


# Попробуем импортировать локальный парсер в разных контекстах (пакет или модуль)
try:
    from backend.ai_parser import local_parse as local_ai_parse
except Exception:
    try:
        from ai_parser import local_parse as local_ai_parse
    except Exception:
        local_ai_parse = None


def _safe_json_loads(raw):
    """
    Пытается безопасно распарсить JSON из ответа модели,
    даже если вокруг есть пояснительный текст или обёртки.
    """
    if isinstance(raw, dict):
        return raw

    if not isinstance(raw, str):
        return None

    candidates = [raw, re.sub(r"```json|```", "", raw).strip()]

    decoder = json.JSONDecoder()

    def _extract_by_braces(s: str):
        """Попробовать найти JSON-объект по балансировке фигурных скобок."""
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

        # Третий проход: извлечь сбалансированный фрагмент по скобкам и пробовать его
        try:
            fragment = _extract_by_braces(candidate)
            if fragment:
                try:
                    return json.loads(fragment)
                except json.JSONDecodeError:
                    # Попробуем безопасно разобрать через ast.literal_eval (поддерживает одинарные кавычки)
                    try:
                        obj = ast.literal_eval(fragment)
                        if isinstance(obj, (dict, list)):
                            return obj
                    except Exception:
                        pass
        except Exception:
            pass

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


def is_task_request(message: str) -> bool:
    """
    Определяет, является ли сообщение запросом на создание задачи.
    """
    message = message.lower().strip()

    # Приветствия и общие фразы - не задачи
    greetings = ['привет', 'здравствуй', 'добрый день', 'добрый вечер', 'доброе утро', 'хай', 'hello', 'hi', 'hey']
    if any(message.startswith(g) or message == g for g in greetings):
        return False

    # Короткие подтверждения - не задачи
    short_confirmations = ['да', 'давай', 'ок', 'окей', 'хорошо', 'согласен', 'согласна', 'ладно', 'понятно', 'ясно']
    if message in short_confirmations:
        return False

    # Вопросы - не задачи (но могут содержать запросы на информацию)
    if any(word in message for word in ['что', 'как', 'когда', 'где', 'почему', 'зачем', 'кто', 'сколько']):
        return False

    # Слова, указывающие на задачу
    task_indicators = [
        'сделай', 'сделать', 'создай', 'создать', 'запланируй', 'запланировать',
        'напомни', 'напомнить', 'добавь', 'добавить', 'поставь', 'поставить',
        'нужно', 'надо', 'требуется', 'необходимо', 'обязательно',
        'встреча', 'совещание', 'митинг', 'звонок', 'позвонить',
        'купить', 'приобрести', 'заказать', 'забронировать'
    ]

    # Временные маркеры - указывают на задачу
    time_indicators = [
        'сегодня', 'завтра', 'послезавтра', 'через', 'в', 'во', 'к',
        'утром', 'вечером', 'днем', 'ночью', 'утро', 'вечер', 'день', 'ночь'
    ]

    has_task_word = any(word in message for word in task_indicators)
    has_time_word = any(word in message for word in time_indicators)

    # Если есть слова задач ИЛИ слова времени - считаем задачей
    return has_task_word or has_time_word


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
        parsed_json = _safe_json_loads(raw_content)

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

        # Если парсинг не удался — попытаемся быстро "починить" ответ модели,
        # вызвав специализированный короткий системный prompt, который вернёт
        # ТОЛЬКО корректный JSON по нужной схеме.
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
                        " \"duration_minutes\": integer|null, \"priority\": string|null, \"category\": string|null}"
                    )
                    repair_user = (
                        "Ниже — сырой ответ модели. Исправь любые форматные ошибки и верни только JSON."
                        f"\n\nСырой ответ:\n{raw_content}"
                    )
                    repair = post_custom(system_prompt=repair_system, user_text=repair_user, max_attempts=1, timeout=6)
                    if repair and repair.get('success') and repair.get('raw'):
                        repaired_raw = repair.get('raw')
                        parsed_json = _safe_json_loads(repaired_raw)
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

            # Вместо того, чтобы возвращать фронтенду техническую ошибку,
            # возвращаем дружелюбный текстовый ответ (чат-формат), чтобы
            # пользователь не видел "Не удалось разобрать ответ модели".
            try:
                return {
                    'success': True,
                    'original_text': user_text,
                    'processed_task': None,
                    'warnings': warnings,
                    'type': 'text',
                    'content': 'Извините, не смог распознать задачу. Можете переформулировать или дать дополнительные подробности?'
                }
            except Exception:
                base_response["error"] = "Не удалось разобрать ответ модели"
                return base_response

        return base_response
    except requests.exceptions.RequestException as exc:
        base_response["error"] = f"Ошибка соединения с GigaChat: {exc}"
        return base_response
    except Exception as exc:
        base_response["error"] = f"Ошибка при обработке запроса: {exc}"
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

def auto_assign_category(title: str, description: str = "") -> str:
    """
    Автоматически определяет категорию задачи на основе её названия и описания.
    Возвращает наиболее подходящую категорию из списка CATEGORIES.
    """
    # Объединяем заголовок и описание для анализа
    text = f"{title} {description}".lower().strip()

    if not text:
        return "Личное"

    # Считаем совпадения ключевых слов для каждой категории
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            # Считаем количество вхождений ключевого слова
            count = text.count(keyword.lower())
            score += count
            # Даем бонус за точное совпадение слов
            if f" {keyword.lower()} " in f" {text} ":
                score += 1
        scores[category] = score

    # Выбираем категорию с максимальным счетом
    best_category = max(scores.items(), key=lambda x: x[1])

    # Если счет равен 0, возвращаем "Личное" как категорию по умолчанию
    if best_category[1] == 0:
        return "Личное"

    return best_category[0]


def suggest_optimal_time(date, description, existing_events, priority="medium"):
    """
    Предлагает оптимальное время для события на основе занятости, типа события и приоритета.
    Учитывает предпочтения пользователя и реальную загруженность дня.
    """
    free_slots = get_free_slots_for_date(date, existing_events)

    if not free_slots:
        return None

    # Анализируем тип события для выбора оптимального времени
    event_type = description.lower()

    # Определяем категории и их предпочтительное время
    time_preferences = {
        'work': {
            'preferred_hours': [9, 10, 11, 14, 15, 16],  # рабочие часы
            'min_duration': 1.0,
            'avoid_hours': [12, 13]  # обеденное время
        },
        'meeting': {
            'preferred_hours': [9, 10, 11, 14, 15, 16],
            'min_duration': 1.0,
            'avoid_hours': [12, 13]
        },
        'lunch': {
            'preferred_hours': [12, 13, 14],
            'min_duration': 0.5,
            'avoid_hours': []
        },
        'sport': {
            'preferred_hours': [7, 8, 9, 18, 19, 20],  # утро или вечер
            'min_duration': 1.0,
            'avoid_hours': []
        },
        'health': {
            'preferred_hours': [8, 9, 10, 17, 18, 19],
            'min_duration': 0.5,
            'avoid_hours': []
        },
        'shopping': {
            'preferred_hours': [10, 11, 15, 16, 17, 18, 19],
            'min_duration': 0.5,
            'avoid_hours': [12, 13, 14]  # обед
        },
        'personal': {
            'preferred_hours': [9, 10, 11, 14, 15, 16, 17, 18, 19],
            'min_duration': 0.5,
            'avoid_hours': []
        }
    }

    # Определяем категорию события
    category = 'personal'  # по умолчанию
    if any(word in event_type for word in ['встреча', 'совещание', 'митинг', 'meeting', 'работа', 'проект', 'бизнес']):
        category = 'work'
    elif any(word in event_type for word in ['обед', 'перерыв', 'пауза', 'кушать', 'поесть']):
        category = 'lunch'
    elif any(word in event_type for word in ['спорт', 'тренировка', 'бег', 'фитнес', 'зал', 'пробежка']):
        category = 'sport'
    elif any(word in event_type for word in ['врач', 'больница', 'аптека', 'здоровье', 'мед']):
        category = 'health'
    elif any(word in event_type for word in ['купить', 'магазин', 'покупки', 'шопинг']):
        category = 'shopping'

    prefs = time_preferences[category]

    # Фильтруем слоты по предпочтениям
    preferred_slots = []
    for slot in free_slots:
        if slot['duration_hours'] >= prefs['min_duration']:
            slot_hour = slot['start'].hour
            if slot_hour in prefs['preferred_hours'] and slot_hour not in prefs['avoid_hours']:
                preferred_slots.append(slot)

    # Если есть предпочтительные слоты, выбираем лучший
    if preferred_slots:
        # Для высокого приоритета - выбираем самое раннее время
        if priority == "high":
            return min(preferred_slots, key=lambda x: x['start'])['start']
        # Для низкого приоритета - выбираем более позднее время
        elif priority == "low":
            return max(preferred_slots, key=lambda x: x['start'])['start']
        # Для среднего - выбираем оптимальное (не слишком рано, не слишком поздно)
        else:
            # Предпочитаем слоты в середине дня
            midday_slots = [s for s in preferred_slots if 10 <= s['start'].hour <= 16]
            if midday_slots:
                return min(midday_slots, key=lambda x: x['start'])['start']
            return preferred_slots[0]['start']

    # Если нет предпочтительных слотов, берем первый доступный
    suitable_slots = [slot for slot in free_slots if slot['duration_hours'] >= prefs['min_duration']]
    if suitable_slots:
        return suitable_slots[0]['start']

    # Если совсем ничего нет, берем любой слот
    if free_slots:
        return free_slots[0]['start']

    return None


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
        # Проверяем, является ли сообщение задачей
        if not is_task_request(message):
            # Это не задача - переходим к обычному чату
            pass  # код ниже обработает как обычный чат
        else:
            event_request = parse_event_request(message)
            if event_request:
                # Это запрос на создание события
                target_date = event_request['date']
                description = event_request['description']

                # Получаем существующие события на эту дату
                from backend.database import Event
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

    # Проверяем, является ли сообщение задачей
    if not is_task_request(message):
        # Это обычное сообщение - переходим к чат-режиму
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

    structured = extract_task_via_gigachat(message, existing_tasks=existing_tasks)

    # Если модель вернула удачно распознанную задачу — предложим пользователю подтверждение
    if structured.get("success"):
        processed = structured["processed_task"] or {}

        # Попытка предложить оптимальное время на основе существующих событий
        suggested_time = None
        try:
            if db_session is not None and user_id is not None and processed:
                # преобразуем дату и description в объекты
                from datetime import datetime as _dt
                date_str = processed.get('date')
                desc = processed.get('title') or processed.get('description') or ''
                priority = processed.get('priority', 'medium')
                if date_str:
                    date_obj = _dt.fromisoformat(date_str).date()
                    # используем локальную функцию suggest_optimal_time
                    suggested = suggest_optimal_time(date_obj, desc, evs if 'evs' in locals() else [], priority)
                    if suggested:
                        suggested_time = suggested.strftime('%H:%M')
        except Exception:
            suggested_time = None

        date_part = processed.get("date")
        time_part = processed.get("time") or (suggested_time or "время не указано")
        title = processed.get("title", "Задача")

        summary = f"Предлагаю добавить: '{title}' на {date_part} {time_part}. Категория: {processed.get('category')}. Приоритет: {processed.get('priority')}"
        if structured.get("warnings"):
            summary += "\nПредупреждения: " + "; ".join(structured["warnings"])

        # Если есть назначений view от модели — включаем их в ответ для фронтенда
        assignments = None
        try:
            raw_model = structured.get('raw_model')
            parsed_raw = _safe_json_loads(raw_model)
            if isinstance(parsed_raw, dict) and parsed_raw.get('assignments'):
                assignments = parsed_raw.get('assignments')
        except Exception:
            assignments = None

        return {
            'type': 'proposal',
            'content': summary,
            'structured': structured,
            'suggested_time': suggested_time,
            'needs_confirmation': True,
            'assignments': assignments
        }

    error_msg = structured.get("error") or "Не удалось обработать запрос"
    return {
        'type': 'text',
        'content': error_msg,
        'structured': structured
    }
