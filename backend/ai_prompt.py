

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union

CATEGORIES = {"Работа", "Учеба", "Личное", "Здоровье", "Покупки", "Встречи"}
PRIORITIES = {"high", "medium", "low"}

VIEWS = {"Работа", "Учеба", "Личное", "Здоровье", "Покупки", "Встречи", "Список"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")

@dataclass(frozen=True)
class TaskOut:
    kind: str
    title: str
    date: str
    time: Optional[str]
    category: str
    priority: str
    assignments: Optional[Dict[str, str]] = None

@dataclass(frozen=True)
class ChatOut:
    kind: str
    message: str
    assignments: Optional[Dict[str, str]] = None
    debug_received: Optional[Dict[str, Any]] = None

ModelOut = Union[TaskOut, ChatOut]

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

    template = f
    return template.strip()

def call_gigachat(system_prompt: str) -> str:
    

    lowered = system_prompt.lower()
    if 'текст пользователя: "привет"' in lowered or 'текст пользователя: "привет!' in lowered:
        return json.dumps(
            {"kind": "chat", "message": "Привет! Напиши задачу или напоминание (например: «Купить хлеб завтра в 10:00»)."},
            ensure_ascii=False,
        )

    return "Предлагаю добавить: 'Без названия' на 2025-12-16 09:00. Категория: Личное. Приоритет: medium"

def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    
    if not text:
        return None
    s = text.strip()

    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass

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
    
    obj = _extract_first_json_object(raw_text)

    if obj is None:

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

    return ChatOut(
        kind="chat",
        message="Похоже, это не задача. Напиши действие и время (например: «Напомни про прививку завтра в 09:00»).",
        assignments=assignments,
        debug_received=obj,
    )

def handle_user_message(user_text: str, existing_tasks: Optional[List[dict]] = None) -> ModelOut:
    
    prompt = build_gigachat_prompt(user_text=user_text, existing_tasks=existing_tasks)
    raw = call_gigachat(prompt)
    return parse_model_response(raw)

if __name__ == "__main__":

    out1 = handle_user_message("привет")
    print("INPUT: привет")
    print(out1)
    print()

    out2 = handle_user_message("абвгд")
    print("INPUT: абвгд")
    print(out2)
    print()

    existing = [
        {"id": 42, "title": "Встреча с командой", "source": "google", "view": ""},
        {"id": 99, "title": "Купить хлеб", "source": "local"},
    ]
    out3 = handle_user_message("ты кто", existing_tasks=existing)
    print("INPUT: ты кто (+existing_tasks)")
    print(out3)
