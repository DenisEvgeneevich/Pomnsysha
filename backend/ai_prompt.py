"""
pomnyasha.py — полный пример “Помняша” пайплайна:

- строим промпт (строгий контракт kind=task|chat)
- вызываем модель (заглушка call_gigachat — вставь свой SDK/HTTP)
- парсим сырой ответ (даже если модель добавила мусор вокруг JSON)
- НИКОГДА не создаём задачу из "привет/ок/абвгд" и т.п.
  (если ответ невалиден/неполон -> превращаем в kind="chat")

ВАЖНО:
Твоя строка вида:
"Предлагаю добавить: 'Без названия' ... Предупреждения: ..."
почти наверняка генерируется ТВОИМ кодом/фронтом как fallback,
когда JSON не распарсился или не прошёл валидацию.
Этот файл показывает, как сделать fallback -> chat, а не "Без названия".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union


# -----------------------------
# Константы/валидация
# -----------------------------

CATEGORIES = {"Работа", "Учеба", "Личное", "Здоровье", "Покупки", "Встречи"}
PRIORITIES = {"high", "medium", "low"}

# Views — для назначения existing_tasks без view/type
VIEWS = {"Работа", "Учеба", "Личное", "Здоровье", "Покупки", "Встречи", "Список"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


# -----------------------------
# Типы ответов
# -----------------------------

@dataclass(frozen=True)
class TaskOut:
    kind: str  # "task"
    title: str
    date: str  # YYYY-MM-DD
    time: Optional[str]  # HH:MM or None
    category: str
    priority: str
    assignments: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class ChatOut:
    kind: str  # "chat"
    message: str
    assignments: Optional[Dict[str, str]] = None
    debug_received: Optional[Dict[str, Any]] = None


ModelOut = Union[TaskOut, ChatOut]


# -----------------------------
# Промпт
# -----------------------------

def build_gigachat_prompt(user_text: str, existing_tasks: Optional[List[dict]] = None) -> str:
    now = datetime.now()
    today_date = now.strftime("%Y-%m-%d")
    tomorrow_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    next_week_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")

    weekday_ru = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ][now.weekday()]

    existing_json = json.dumps(existing_tasks, ensure_ascii=False, default=str) if existing_tasks else "null"

    template = f"""
Ты — «Помняша», ИИ-ассистент для планирования задач. Ты получаешь короткий текст на русском и ДОЛЖЕН вернуть строго один валидный JSON-объект. Никакого текста вокруг JSON. Никаких markdown-блоков. Никаких пояснений. Только JSON.

КРИТИЧЕСКИ ВАЖНО:
1) Ты ВСЕГДА отвечаешь JSON-объектом (даже если это приветствие, "ты кто", бессмыслица, благодарность).
2) Если это не задача — верни kind="chat" и поле message (строка).
3) Если это задача/напоминание/встреча/покупка — верни kind="task" и поля: title,date,time,category,priority.
4) Если сомневаешься — выбирай kind="chat" (не выдумывай задачу).

Контракт ответа (строго):

- Для задачи:
{{
  "kind": "task",
  "title": "…",
  "date": "YYYY-MM-DD",
  "time": "HH:MM" | null,
  "category": one of ["Работа","Учеба","Личное","Здоровье","Покупки","Встречи"],
  "priority": one of ["high","medium","low"],
  "assignments": {{ "<id>": "<view>" }}   // опционально
}}

- Для обычного чата (не задача):
{{
  "kind": "chat",
  "message": "…",
  "assignments": {{ "<id>": "<view>" }}   // опционально
}}

Правила даты/времени:
- Если дата не указана явно — подставь "{today_date}".
- "сегодня" -> "{today_date}"
- "завтра" -> "{tomorrow_date}"
- "через неделю" -> "{next_week_date}"
- time: только "HH:MM" или null.

Категории:
- category строго одна из ["Работа","Учеба","Личное","Здоровье","Покупки","Встречи"].
- Если не уверен — выбирай наиболее вероятную.

Приоритет:
- "срочно", "важно", "ASAP" -> high
- обычно -> medium
- "может быть", "когда-нибудь", "если успею" -> low

Existing tasks (если переданы):
{existing_json}

Если existing_tasks не null:
- Назначь view для задач без view/type (или пустых).
- view выбирай из ["Работа","Учеба","Личное","Здоровье","Покупки","Встречи","Список"].
- Верни объект assignments: {{"<id>":"<view>"}}.
- assignments можно добавить и в task, и в chat.

Примеры:

# 1) Приветствие / бессмыслица -> chat
Вход: "Привет"
Выход:
{
    "kind": "chat",
    "message": "Привет! Напиши задачу или напоминание (например: \"Купить хлеб завтра в 10:00\")."
}

# 2) Короткое подтверждение -> chat (не создавать задачу)
Вход: "ок"
Выход:
{
    "kind": "chat",
    "message": "Ок! Сформулируй, пожалуйста, задачу: что сделать и когда."
}

# 3) Задача с относительной датой и временем
Вход: "Купить хлеб завтра в 09:00"
Выход:
{
    "kind": "task",
    "title": "Купить хлеб",
    "date": "{tomorrow_date}",
    "time": "09:00",
    "category": "Покупки",
    "priority": "medium"
}

# 4) Задача с ISO-датой и временем
Вход: "Встреча 2025-12-24 15:30 с командой"
Выход:
{
    "kind": "task",
    "title": "Встреча с командой",
    "date": "2025-12-24",
    "time": "15:30",
    "category": "Работа",
    "priority": "high"
}

# 5) Задача без времени -> time = null
Вход: "Напомни поменять масло 2025-12-20"
Выход:
{
    "kind": "task",
    "title": "Поменять масло",
    "date": "2025-12-20",
    "time": null,
    "category": "Личное",
    "priority": "medium"
}

# 6) Пример assignments при существующих задачах
Вход: "Распределить задачи по папкам"
(existing_tasks переданы)
Выход:
{
    "kind": "chat",
    "message": "Я предложил назначения для некоторых задач.",
    "assignments": {"42": "Работа", "99": "Покупки"}
}

# Примечания к примерам:
# - Всегда используйте null для отсутствующего времени.
# - Поле title должно быть короткой читабельной строкой, без окружающих кавычек.
# - НЕ возвращайте дополнительные поля, кроме перечисленных в контракте.

ТЕКСТ ПОЛЬЗОВАТЕЛЯ: "{user_text}"
Сегодня: "{today_date}", день недели: "{weekday_ru}".
"""
    return template.strip()


# -----------------------------
# Вызов модели (заглушка)
# -----------------------------

def call_gigachat(system_prompt: str) -> str:
    """
    Заменить на реальный вызов GigaChat/LLM.
    Важно: возвращай СЫРОЙ текст ответа модели (строку), как есть.

    Ниже — демо-заглушка, чтобы файл был запускаемым.
    """
    # ДЕМО: эмулируем правильное поведение на "привет"
    lowered = system_prompt.lower()
    if 'текст пользователя: "привет"' in lowered or 'текст пользователя: "привет!' in lowered:
        return json.dumps(
            {"kind": "chat", "message": "Привет! Напиши задачу или напоминание (например: «Купить хлеб завтра в 10:00»)."},
            ensure_ascii=False,
        )
    # ДЕМО: эмулируем “плохой” ответ (как в твоём логе) — не JSON
    return "Предлагаю добавить: 'Без названия' на 2025-12-16 09:00. Категория: Личное. Приоритет: medium"


# -----------------------------
# Парсинг/нормализация ответа
# -----------------------------

def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Пытается вытащить первый JSON-объект из строки.
    Переживает мусор до/после JSON.
    """
    if not text:
        return None
    s = text.strip()

    # Быстрый путь: строка — чистый JSON-объект
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass

    # Поиск первой "{" и последней "}" — грубо, но работает в 90% случаев
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = s[start : end + 1]
    try:
        obj = json.loads(candidate)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_assignments(obj: Dict[str, Any]) -> Optional[Dict[str, str]]:
    a = obj.get("assignments")
    if a is None:
        return None
    if not isinstance(a, dict):
        return None
    out: Dict[str, str] = {}
    for k, v in a.items():
        if k is None:
            continue
        ks = str(k)
        if not isinstance(v, str):
            continue
        vs = v.strip()
        if not vs:
            continue
        # при желании можно жёстко ограничить VIEWS:
        if vs not in VIEWS:
            continue
        out[ks] = vs
    return out or None


def _is_valid_task_dict(obj: Dict[str, Any]) -> Tuple[bool, str]:
    if obj.get("kind") != "task":
        return False, "kind != task"

    title = obj.get("title")
    date = obj.get("date")
    time = obj.get("time")
    category = obj.get("category")
    priority = obj.get("priority")

    if not isinstance(title, str) or not title.strip():
        return False, "bad title"
    if not isinstance(date, str) or not _DATE_RE.match(date):
        return False, "bad date"
    if time is not None and (not isinstance(time, str) or not _TIME_RE.match(time)):
        return False, "bad time"
    if category not in CATEGORIES:
        return False, "bad category"
    if priority not in PRIORITIES:
        return False, "bad priority"

    return True, "ok"


def _is_valid_chat_dict(obj: Dict[str, Any]) -> Tuple[bool, str]:
    if obj.get("kind") != "chat":
        return False, "kind != chat"
    msg = obj.get("message")
    if not isinstance(msg, str) or not msg.strip():
        return False, "bad message"
    return True, "ok"


def parse_model_response(raw_text: str) -> ModelOut:
    """
    Главная гарантия: если ответ модели невалиден/не JSON/неполный,
    то возвращаем kind="chat", а НЕ "Без названия" задачу.
    """
    obj = _extract_first_json_object(raw_text)

    if obj is None:
        # Вот тут раньше у тебя, судя по логу, делался fallback в "Без названия".
        # Мы делаем fallback в chat.
        return ChatOut(
            kind="chat",
            message="Я тебя понял, но это не похоже на задачу. Напиши, пожалуйста, что нужно сделать и когда (например: «Купить хлеб завтра в 10:00»).",
        )

    assignments = _normalize_assignments(obj)

    ok_task, _ = _is_valid_task_dict(obj)
    if ok_task:
        return TaskOut(
            kind="task",
            title=obj["title"].strip(),
            date=obj["date"],
            time=obj.get("time"),
            category=obj["category"],
            priority=obj["priority"],
            assignments=assignments,
        )

    ok_chat, _ = _is_valid_chat_dict(obj)
    if ok_chat:
        return ChatOut(
            kind="chat",
            message=obj["message"].strip(),
            assignments=assignments,
        )

    # Любая “полу-задача”/мусорный JSON -> chat
    return ChatOut(
        kind="chat",
        message="Похоже, это не задача. Напиши действие и время (например: «Напомни про прививку завтра в 09:00»).",
        assignments=assignments,
        debug_received=obj,
    )


# -----------------------------
# Единая точка входа (обработчик сообщения)
# -----------------------------

def handle_user_message(user_text: str, existing_tasks: Optional[List[dict]] = None) -> ModelOut:
    """
    1) строим промпт
    2) вызываем модель
    3) парсим и нормализуем ответ
    """
    prompt = build_gigachat_prompt(user_text=user_text, existing_tasks=existing_tasks)
    raw = call_gigachat(prompt)
    return parse_model_response(raw)


# -----------------------------
# Пример запуска
# -----------------------------

if __name__ == "__main__":
    # Пример 1: привет -> chat
    out1 = handle_user_message("привет")
    print("INPUT: привет")
    print(out1)
    print()

    # Пример 2: "плохой" не-JSON ответ -> chat (а не "Без названия")
    out2 = handle_user_message("абвгд")
    print("INPUT: абвгд")
    print(out2)
    print()

    # Если хочешь проверить существующие задачи для assignments:
    existing = [
        {"id": 42, "title": "Встреча с командой", "source": "google", "view": ""},
        {"id": 99, "title": "Купить хлеб", "source": "local"},
    ]
    out3 = handle_user_message("ты кто", existing_tasks=existing)
    print("INPUT: ты кто (+existing_tasks)")
    print(out3)
