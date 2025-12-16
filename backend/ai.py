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
    return f

def parse_event_request(message: str) -> dict:
    
    message = message.lower().strip()

    date_patterns = {
        'сегодня': 0,
        'завтра': 1,
        'послезавтра': 2,
        'через день': 1,
        'через два дня': 2,
        'через три дня': 3,
        'через неделю': 7
    }

    target_date = None
    for pattern, days_offset in date_patterns.items():
        if pattern in message:
            target_date = (datetime.now() + timedelta(days=days_offset)).date()
            break

    date_match = re.search(r'(\d{1,2})[.\-](\d{1,2})(?:[.\-](\d{2,4}))?', message)
    if date_match:
        day, month = int(date_match.group(1)), int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else datetime.now().year

        if year < 100:
            year += 2000

        try:
            target_date = datetime(year, month, day).date()
        except ValueError:
            pass

    if not target_date:
        return None

    time_match = re.search(r'(\d{1,2})[:\.](\d{2})', message)
    requested_time = None
    if time_match:
        hours, minutes = int(time_match.group(1)), int(time_match.group(2))
        try:
            requested_time = datetime.strptime(f"{hours:02d}:{minutes:02d}", "%H:%M").time()
        except ValueError:
            pass

    description = message
    for pattern in date_patterns.keys():
        description = description.replace(pattern, '')

    description = re.sub(r'\d{1,2}[.\-:]\d{1,2}(?:[.\-]\d{2,4})?', '', description)
    description = re.sub(r'\d{1,2}[:\.]\d{2}', '', description)
    description = re.sub(r'\s+', ' ', description).strip()

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

try:
    from backend.ai_parser import local_parse as local_ai_parse
except Exception:
    try:
        from ai_parser import local_parse as local_ai_parse
    except Exception:
        local_ai_parse = None

def _safe_json_loads(raw):
    
    if isinstance(raw, dict):
        return raw

    if not isinstance(raw, str):
        return None

    candidates = [raw, re.sub(r"```json|```", "", raw).strip()]

    decoder = json.JSONDecoder()

    def _extract_by_braces(s: str):
        
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

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        brace_index = candidate.find("{")
        while brace_index != -1:
            try:
                obj, _ = decoder.raw_decode(candidate[brace_index:])
                return obj
            except json.JSONDecodeError:
                brace_index = candidate.find("{", brace_index + 1)

        try:
            fragment = _extract_by_braces(candidate)
            if fragment:
                try:
                    return json.loads(fragment)
                except json.JSONDecodeError:

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
    
    message = message.lower().strip()

    greetings = ['привет', 'здравствуй', 'добрый день', 'добрый вечер', 'доброе утро', 'хай', 'hello', 'hi', 'hey']
    if any(message.startswith(g) or message == g for g in greetings):
        return False

    short_confirmations = ['да', 'давай', 'ок', 'окей', 'хорошо', 'согласен', 'согласна', 'ладно', 'понятно', 'ясно']
    if message in short_confirmations:
        return False

    if any(word in message for word in ['что', 'как', 'когда', 'где', 'почему', 'зачем', 'кто', 'сколько']):
        return False

    task_indicators = [
        'сделай', 'сделать', 'создай', 'создать', 'запланируй', 'запланировать',
        'напомни', 'напомнить', 'добавь', 'добавить', 'поставь', 'поставить',
        'нужно', 'надо', 'требуется', 'необходимо', 'обязательно',
        'встреча', 'совещание', 'митинг', 'звонок', 'позвонить',
        'купить', 'приобрести', 'заказать', 'забронировать'
    ]

    time_indicators = [
        'сегодня', 'завтра', 'послезавтра', 'через', 'в', 'во', 'к',
        'утром', 'вечером', 'днем', 'ночью', 'утро', 'вечер', 'день', 'ночь'
    ]

    has_task_word = any(word in message for word in task_indicators)
    has_time_word = any(word in message for word in time_indicators)

    return has_task_word or has_time_word

def extract_task_via_gigachat(user_text: str, existing_tasks: list = None) -> dict:
    base_response = {
        "success": False,
        "original_text": user_text,
        "processed_task": None,
        "warnings": []
    }

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

        pass

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

    try:
        load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
    except Exception:

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

        prompt = None
        try:
            try:
                from backend.ai_prompt import build_gigachat_prompt
            except Exception:
                from ai_prompt import build_gigachat_prompt
            prompt = build_gigachat_prompt(user_text, existing_tasks=existing_tasks)
        except Exception:

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

        if not ok:
            local_fallback = None
            try:
                local_fallback = local_ai_parse(user_text)
            except Exception:
                local_fallback = None

            if local_fallback:

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

                try:

                    try:
                        from backend.ai_client import post_conversation
                    except Exception:
                        from ai_client import post_conversation

                    conv = post_conversation(user_text)
                    if conv.get('success') and conv.get('raw'):

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
    

    work_start = datetime.combine(date, datetime.strptime("09:00", "%H:%M").time())
    work_end = datetime.combine(date, datetime.strptime("18:00", "%H:%M").time())

    sorted_events = sorted(existing_events, key=lambda x: x.start_time)

    free_slots = []
    current_time = work_start

    for event in sorted_events:
        event_start = event.start_time
        event_end = event.end_time or event.start_time

        if event_start > current_time:
            slot_duration = (event_start - current_time).total_seconds() / 3600
            if slot_duration >= 0.5:
                free_slots.append({
                    'start': current_time,
                    'end': event_start,
                    'duration_hours': slot_duration
                })

        current_time = max(current_time, event_end)

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

            score += text.count(kw)
            if f" {kw} " in f" {text} ":
                score += 2
        scores[category] = score

    best_category, best_score = max(scores.items(), key=lambda x: x[1])
    if best_score <= 0:
        return "Личное"
    return best_category

def suggest_optimal_time(date, description, existing_events, priority: str = "medium"):
    
    return suggest_optimal_time_with_exclusions(date, description, existing_events, priority, [])

def suggest_optimal_time_with_exclusions(date, description, existing_events, priority: str = "medium", exclude_times: list = None):
    
    if exclude_times is None:
        exclude_times = []

    free_slots = get_free_slots_for_date(date, existing_events)
    if not free_slots:
        return None

    event_type = (description or "").lower()

    time_prefs_by_category = {
        "work": [9, 10, 11, 14, 15, 16],
        "lunch": [12, 13, 14],
        "sport": [7, 8, 18, 19, 20],
        "health": [9, 10, 11, 17, 18],
        "shopping": [11, 12, 17, 18, 19],
        "personal": [10, 11, 17, 18, 19],
    }

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

    exclude_datetimes = []
    for time_str in exclude_times:
        try:
            if isinstance(time_str, str) and ':' in time_str:
                hour, minute = map(int, time_str.split(':'))
                exclude_datetimes.append(datetime.combine(date, datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()))
        except Exception:
            pass

    candidates = []

    for slot in free_slots:
        start_hour = slot["start"].hour
        end_hour = slot["end"].hour
        for h in preferred_hours:
            if start_hour <= h < end_hour:
                candidate = datetime.combine(date, datetime.strptime(f"{h:02d}:00", "%H:%M").time())

                if not any(abs((candidate - excl).total_seconds()) < 1800 for excl in exclude_datetimes):
                    candidates.append(candidate)

    if not candidates:
        for slot in free_slots:
            current = slot["start"]
            while current < slot["end"]:

                if not any(abs((current - excl).total_seconds()) < 1800 for excl in exclude_datetimes):
                    candidates.append(current)
                current += timedelta(minutes=30)
                if len(candidates) >= 10:
                    break
            if len(candidates) >= 10:
                break

    if not candidates:
        return None

    candidates.sort()

    if priority == "high":
        return candidates[0]
    if priority == "low":
        return candidates[-1]

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
    

    load_dotenv()
    global AUTHORIZATION_KEY
    AUTHORIZATION_KEY = os.getenv("GIGACHAT_AUTHORIZATION_KEY")

    global TOKEN_CACHE
    TOKEN_CACHE = None

    if db_session and user_id:

        if not is_task_request(message):

            pass
        else:
            event_request = parse_event_request(message)
            if event_request:

                target_date = event_request['date']
                description = event_request['description']

                from backend.database import Event
                existing_events = db_session.query(Event).filter(
                    Event.user_id == user_id,
                    Event.start_time >= datetime.combine(target_date, datetime.min.time()),
                    Event.start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
                ).all()

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

    if not is_task_request(message):

        try:

            try:
                from backend.ai_client import post_conversation
            except Exception:
                from ai_client import post_conversation

            conv = post_conversation(message)
            if conv.get('success') and conv.get('raw'):

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

    if structured.get("success"):
        processed = structured["processed_task"] or {}

        suggested_time = None
        try:
            if db_session is not None and user_id is not None and processed:

                from datetime import datetime as _dt
                date_str = processed.get('date')
                desc = processed.get('title') or processed.get('description') or ''
                priority = processed.get('priority', 'medium')
                if date_str:
                    date_obj = _dt.fromisoformat(date_str).date()

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
