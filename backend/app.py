import os
import sys
import secrets

# Ensure project root is on sys.path so module imports like `backend.xxx` work
# even when uvicorn is started from inside the `backend/` directory.
try:
    _THIS_DIR = os.path.dirname(__file__)
    _PROJECT_ROOT = os.path.dirname(_THIS_DIR)
    if _PROJECT_ROOT and _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
except Exception:
    pass
from datetime import datetime, timedelta
from typing import Dict, Any
from dateutil import parser as dtparser

from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from backend.database import get_db, create_tables, Event, get_user_creds, save_user_creds
from backend.google_calendar import (
    create_google_event,
    delete_google_event,
    sync_google_calendar,
    upsert_google_event
)
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest

from backend.ai import ask_gigachat


CLIENT_SECRETS_FILE = os.path.join("secrets", "client_secret.json")
SCOPES = ["https://www.googleapis.com/auth/calendar",
          "https://www.googleapis.com/auth/calendar.events"]
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/oauth2/callback")

app = FastAPI(title="Помняша Backend")


origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id"],
)

# Простое временное хранилище pending proposals по сессии (in-memory).
# Ключ — sid (int), значение — structured object, возвращённый моделью при предложении.
pending_proposals: dict = {}



def _parse_dt(val: str) -> datetime:
    if val.endswith("Z"):
        val = val.replace("Z", "+00:00")
    dt = dtparser.parse(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt


def _get_or_create_session(request: Request) -> tuple[int, bool]:
    header_sid = request.headers.get("x-session-id")
    if header_sid and header_sid.isdigit():
        return int(header_sid), False

    sid = request.cookies.get("sid")
    if sid and sid.isdigit():
        return int(sid), False

    return secrets.randbits(63), True


def _persist_session(response: Response, sid: int):
    response.set_cookie(
        "sid",
        str(sid),
        httponly=True,
        samesite="Lax",
        secure=False
    )
    response.headers["X-Session-Id"] = str(sid)



@app.get("/oauth2/login")
def oauth_login(request: Request):
    user_id, _ = _get_or_create_session(request)

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )

    resp = RedirectResponse(auth_url)
    _persist_session(resp, user_id)

    return resp


@app.get("/oauth2/callback")
def oauth_callback(request: Request, db: Session = Depends(get_db)):
    code = request.query_params.get("code")
    if not code:
        return JSONResponse({"error": "missing code"}, status_code=400)

    try:
        user_id, _ = _get_or_create_session(request)

        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)

        creds = flow.credentials
        save_user_creds(user_id, creds)

        sync_google_calendar(user_id)

        local_events = db.query(Event).filter(
            Event.user_id == user_id,
            Event.external_id.is_(None)
        ).all()

        for ev in local_events:
            gid = create_google_event(user_id, {
                "title": ev.title,
                "description": ev.description or "",
                "start": ev.start_time.isoformat(),
                "end": ev.end_time.isoformat()
            })
            if gid:
                ev.external_id = gid
                ev.source = "google"

        db.commit()

        resp = RedirectResponse("http://localhost:3000")
        _persist_session(resp, user_id)

        return resp

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)



@app.get("/me")
def me(request: Request, response: Response):
    sid = request.headers.get("x-session-id")
    if not (sid and sid.isdigit()):
        sid_cookie = request.cookies.get("sid")
        if sid_cookie and sid_cookie.isdigit():
            sid = sid_cookie
        else:
            return {"authorized": False}

    user_id = int(sid)
    creds = get_user_creds(user_id)
    if not creds:
        return {"authorized": False}

    if not creds.valid:
        try:
            creds.refresh(GoogleRequest())
            save_user_creds(user_id, creds)
        except:
            return {"authorized": False}

    _persist_session(response, user_id)
    return {"authorized": True}



@app.get("/events")
def get_events(request: Request, response: Response, db: Session = Depends(get_db)):
    user_id, _ = _get_or_create_session(request)
    _persist_session(response, user_id)

    events = db.query(Event).filter(Event.user_id == user_id).all()

    return [{
        "id": e.id,
        "title": e.title,
        "description": e.description or "",
        "start": e.start_time.isoformat(),
        "end": e.end_time.isoformat(),
        "source": e.source,
        "view": getattr(e, 'view', None)
    } for e in events]


@app.post("/events")
def create_event(
    data: Dict[str, Any],
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        title = data.get("title", "Без названия")
        description = data.get("description") or ""

        start = _parse_dt(data["start"])
        end = _parse_dt(data.get("end", data["start"]))

        ev = Event(
            user_id=user_id,
            title=title,
            description=description,
            start_time=start,
            end_time=end,
            source="local"
        )

        db.add(ev)
        db.commit()
        db.refresh(ev)

        gid = upsert_google_event(user_id, ev)
        if gid:
            ev.external_id = gid
            ev.source = "google"
            db.commit()

        sync_google_calendar(user_id)

        return {"status": "ok", "id": ev.id}

    except Exception as e:
        return JSONResponse({"error": f"create_event failed: {e}"}, status_code=400)


@app.put("/events/{event_id}")
def update_event(
    event_id: int,
    data: Dict[str, Any],
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        ev = db.query(Event).filter(
            Event.id == event_id,
            Event.user_id == user_id
        ).first()

        if not ev:
            raise HTTPException(status_code=404)

        ev.title = data.get("title", ev.title)
        ev.description = data.get("description", ev.description)

        if "start" in data:
            ev.start_time = _parse_dt(data["start"])
        if "end" in data:
            ev.end_time = _parse_dt(data["end"])

        db.commit()
        db.refresh(ev)

        upsert_google_event(user_id, ev)
        sync_google_calendar(user_id)

        return {"status": "updated"}

    except Exception as e:
        return JSONResponse({"error": f"update_event failed: {e}"}, status_code=400)


@app.delete("/events/{event_id}")
def delete_event(event_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        ev = db.query(Event).filter(
            Event.id == event_id,
            Event.user_id == user_id
        ).first()

        if not ev:
            raise HTTPException(404)

        delete_google_event(user_id, ev)
        db.delete(ev)
        db.commit()

        sync_google_calendar(user_id)

        return {"status": "deleted"}

    except Exception as e:
        return JSONResponse({"error": f"delete_event failed: {e}"}, status_code=400)



@app.get("/sync")
def do_sync(request: Request, response: Response):
    user_id, _ = _get_or_create_session(request)
    _persist_session(response, user_id)
    sync_google_calendar(user_id)
    return {"status": "ok"}


@app.post("/suggest-times")
def suggest_times(data: Dict[str, Any], request: Request, response: Response, db: Session = Depends(get_db)):
    """Возвращает список предложенных времён на заданную дату на основе свободных слотов.

    Ожидает JSON: { date: "YYYY-MM-DD", description: "...", count?: int }
    Возвращает: { times: ["HH:MM", ...] }
    """
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        date_str = data.get("date")
        if not date_str:
            return JSONResponse({"error": "missing date"}, status_code=400)

        from datetime import datetime as _dt
        target_date = _dt.fromisoformat(date_str).date()

        # Получаем существующие события на эту дату
        from database import Event
        existing_events = db.query(Event).filter(
            Event.user_id == user_id,
            Event.start_time >= datetime.combine(target_date, datetime.min.time()),
            Event.start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
        ).all()

        free_slots = []
        try:
            free_slots = get_free_slots_for_date(target_date, existing_events)
        except Exception:
            free_slots = []

        # Генерируем список предложенных времён (шаг 30 минут)
        count = int(data.get("count", 5))
        suggestions = []
        for slot in free_slots:
            start_dt = slot["start"]
            dur_hours = slot["duration_hours"]
            steps = max(1, int(dur_hours * 2))
            for i in range(steps):
                t = start_dt + timedelta(minutes=30 * i)
                suggestions.append(t.strftime("%H:%M"))
                if len(suggestions) >= count:
                    break
            if len(suggestions) >= count:
                break

        # Если нет слотов — вернуть пустой список
        return {"times": suggestions}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)



@app.get("/stats")
def get_stats(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        # Получаем все события пользователя
        events = db.query(Event).filter(Event.user_id == user_id).all()

        # Статистика по дням недели
        day_names = ['ПОНЕДЕЛЬНИК', 'ВТОРНИК', 'СРЕДА', 'ЧЕТВЕРГ', 'ПЯТНИЦА', 'СУББОТА', 'ВОСКРЕСЕНЬЕ']
        day_stats = {i: 0 for i in range(7)}

        for event in events:
            day_of_week = event.start_time.weekday()  # 0 = Monday, 6 = Sunday
            day_stats[day_of_week] += 1

        # Преобразуем в формат для frontend
        weekly_stats = []
        max_tasks = max(day_stats.values()) if day_stats else 0

        for i, day_name in enumerate(day_names):
            tasks_count = day_stats[i]
            weekly_stats.append({
                'day': day_name,
                'tasks': tasks_count,
                'isMostBusy': tasks_count == max_tasks and tasks_count > 0
            })

        # Категории задач (анализ по ключевым словам)
        categories = {
            'Работа': ['работа', 'проект', 'встреча', 'совещание', 'бизнес', 'офис'],
            'Семья': ['семья', 'родители', 'дети', 'дом', 'ужин', 'завтрак'],
            'Друзья': ['друзья', 'встреча с', 'поход', 'кафе', 'кино', 'театр'],
            'Быт': ['покупки', 'магазин', 'уборка', 'стирка', 'ремонт', 'быт'],
            'Спорт': ['спорт', 'тренировка', 'бег', 'фитнес', 'зал'],
            'Учеба': ['учеба', 'урок', 'экзамен', 'лекция', 'домашнее задание']
        }

        category_stats = {cat: 0 for cat in categories.keys()}
        other_count = 0

        for event in events:
            title_lower = (event.title or '').lower()
            description_lower = (event.description or '').lower()
            text = f"{title_lower} {description_lower}"

            found_category = False
            for category, keywords in categories.items():
                if any(keyword in text for keyword in keywords):
                    category_stats[category] += 1
                    found_category = True
                    break

            if not found_category:
                other_count += 1

        # Преобразуем в формат для круговой диаграммы
        total_events = len(events)
        if total_events > 0:
            pie_data = []
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F', '#BB8FCE']

            color_index = 0
            for category, count in category_stats.items():
                if count > 0:
                    percentage = round((count / total_events) * 100)
                    pie_data.append({
                        'name': category,
                        'value': percentage,
                        'color': colors[color_index % len(colors)]
                    })
                    color_index += 1

            if other_count > 0:
                percentage = round((other_count / total_events) * 100)
                pie_data.append({
                    'name': 'Другое',
                    'value': percentage,
                    'color': colors[color_index % len(colors)]
                })
        else:
            pie_data = []

        # Находим самый загруженный день
        most_busy_day = None
        if weekly_stats:
            busy_days = [day for day in weekly_stats if day['isMostBusy']]
            if busy_days:
                most_busy_day = busy_days[0]

        return {
            'weeklyStats': weekly_stats,
            'pieData': pie_data,
            'mostBusyDay': most_busy_day,
            'totalEvents': total_events
        }

    except Exception as e:
        return JSONResponse({"error": f"stats failed: {e}"}, status_code=400)


@app.get("/debug/all_events")
def debug_all_events(db: Session = Depends(get_db)):
    """DEV endpoint: возвращает все события из БД (только для локальной отладки)."""
    try:
        events = db.query(Event).all()
        return [{
            "id": e.id,
            "user_id": e.user_id,
            "title": e.title,
            "start": e.start_time.isoformat(),
            "end": e.end_time.isoformat() if e.end_time else None,
            "source": e.source,
            "external_id": e.external_id,
        } for e in events]
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/debug/user_events/{user_id}")
def debug_user_events(user_id: int, db: Session = Depends(get_db)):
    """DEV endpoint: возвращает все события для указанного user_id."""
    try:
        events = db.query(Event).filter(Event.user_id == user_id).all()
        return [{
            "id": e.id,
            "user_id": e.user_id,
            "title": e.title,
            "start": e.start_time.isoformat(),
            "end": e.end_time.isoformat() if e.end_time else None,
            "source": e.source,
            "external_id": e.external_id,
        } for e in events]
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/chat")
def chat_endpoint(data: Dict[str, Any], request: Request, response: Response, db: Session = Depends(get_db)):
    msg = data.get("message", "")

    # Получаем пользователя из сессии
    user_id, _ = _get_or_create_session(request)
    _persist_session(response, user_id)

    # Если сообщение — короткое подтверждение (например: 'давай', 'ок', 'хорошо', 'да'),
    # и у нас есть отложенное предложение для этой сессии — сразу создаём событие.
    short_accepts = {'да', 'давай', 'ок', 'окей', 'хорошо', 'согласен', 'согласна'}
    msg_norm = (msg or '').strip().lower()

    # Сохраним/персистим сессию cookie
    resp = {}

    if msg_norm in short_accepts:
        sid, created = _get_or_create_session(request)
        # Попробуем найти отложенное предложение
        proposal = pending_proposals.get(sid)
        if proposal and isinstance(proposal, dict):
            # создаём событие в БД
            try:
                # ожидаем, что proposal содержит processed_task
                processed = proposal.get('processed_task') or proposal
                date_str = processed.get('date')
                time_str = processed.get('time')
                title = processed.get('title') or processed.get('description') or 'Задача'

                if not date_str:
                    return {"reply": {"type": "text", "content": "Не удалось определить дату для события."}}

                if not time_str:
                    # если времени нет — ставим 09:00 по умолчанию
                    time_str = '09:00'

                event_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")

                new_event = Event(
                    user_id=user_id,
                    title=title,
                    description=processed.get('description') or title,
                    start_time=event_datetime,
                    end_time=event_datetime,
                    source="ai_assistant"
                )

                db.add(new_event)
                db.commit()
                db.refresh(new_event)

                # обновим google, если нужно
                try:
                    sync_google_calendar(user_id)
                except Exception:
                    pass

                # удалим отложенное предложение
                try:
                    del pending_proposals[sid]
                except Exception:
                    pass

                return {"reply": {"type": "text", "content": f"✅ Событие '{title}' добавлено на {event_datetime.strftime('%d.%m.%Y %H:%M')}", "event_id": new_event.id}}
            except Exception as e:
                return {"reply": {"type": "text", "content": f"Ошибка при создании события: {e}"}}

    # Иначе — вызываем улучшенную версию ask_gigachat
    result = ask_gigachat(msg, db_session=db, user_id=user_id)

    # Если модель вернула предложение с подтверждением — сохраняем его в pending_proposals
    try:
        if isinstance(result, dict) and result.get('type') == 'proposal' and result.get('needs_confirmation'):
            sid, _ = _get_or_create_session(request)
            pending_proposals[sid] = result
    except Exception:
        pass

    # Если модель назвала это не задачей (или не вернула processed_task),
    # попробуем дать полноценный чат-ответ через conversational API.
    try:
        if isinstance(result, dict) and (result.get('processed_task') is None) and result.get('type') == 'text':
            try:
                from backend.ai_client import post_conversation
            except Exception:
                try:
                    from ai_client import post_conversation
                except Exception:
                    post_conversation = None

            if post_conversation:
                conv = post_conversation(msg)
                if conv and conv.get('success') and conv.get('raw'):
                    return {"reply": {"type": "text", "content": conv.get('raw')}}
    except Exception:
        pass

    return {"reply": result}


@app.post("/assignments")
def save_assignments(data: Dict[str, Any], request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Принимает map `assignments`: {"<event_id>": "<view>"} и сохраняет поле `view` в БД.
    """
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        assignments = data.get('assignments') or {}
        if not isinstance(assignments, dict):
            return JSONResponse({"error": "assignments must be an object"}, status_code=400)

        updated = 0
        for sid, view in assignments.items():
            try:
                eid = int(sid)
            except Exception:
                continue
            ev = db.query(Event).filter(Event.id == eid, Event.user_id == user_id).first()
            if not ev:
                continue
            ev.view = view
            updated += 1

        db.commit()
        return {"status": "ok", "updated": updated}
    except Exception as e:
        return JSONResponse({"error": f"save_assignments failed: {e}"}, status_code=400)


@app.get('/parse-failures')
def parse_failures(request: Request):
    """Возвращает простую метрику: сколько было записей parse_failed и первые 50 записей."""
    try:
        import json as _json, os
        log_path = os.path.join(os.path.dirname(__file__), 'ai_parse_errors.log')
        if not os.path.exists(log_path):
            return {"count": 0, "entries": []}

        entries = []
        with open(log_path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                except Exception:
                    continue
                if obj.get('type') == 'parse_failed':
                    entries.append(obj)
                if len(entries) >= 50:
                    break

        # Подсчитаем общее количество записей parse_failed (медленно: читаем файл)
        total = 0
        with open(log_path, 'r', encoding='utf-8') as fh:
            for line in fh:
                try:
                    obj = _json.loads(line)
                    if obj.get('type') == 'parse_failed':
                        total += 1
                except Exception:
                    continue

        return {"count": total, "entries": entries}
    except Exception as e:
        return JSONResponse({"error": f"parse_failures failed: {e}"}, status_code=500)


@app.post("/confirm-event")
def confirm_event(data: Dict[str, Any], request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        date_str = data.get("date")
        time_str = data.get("time")
        description = data.get("description", "")

        if not date_str or not time_str:
            return {"success": False, "message": "Не указаны дата или время"}

        # Парсим дату и время
        try:
            event_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")
        except ValueError:
            return {"success": False, "message": "Неверный формат даты или времени"}

        # Создаем событие
        new_event = Event(
            user_id=user_id,
            title=description,
            description=description,
            start_time=event_datetime,
            end_time=event_datetime,  # Для простоты, события без длительности
            source="ai_assistant"
        )

        db.add(new_event)
        db.commit()
        db.refresh(new_event)

        # Синхронизируем с Google Calendar
        try:
            sync_google_calendar(user_id)
        except Exception as e:
            print(f"Ошибка синхронизации с Google Calendar: {e}")

        return {
            "success": True,
            "message": f"Событие '{description}' успешно добавлено на {event_datetime.strftime('%d.%m.%Y %H:%M')}",
            "event_id": new_event.id
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "message": f"Ошибка при создании события: {str(e)}"}


@app.on_event("startup")
def startup():
    create_tables()
    print("База готова")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
