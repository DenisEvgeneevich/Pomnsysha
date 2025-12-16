import os
import sys
import secrets

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

from backend.database import get_db, create_tables, Event, get_user_creds, save_user_creds, ensure_user_exists
from backend.google_calendar import (
    create_google_event,
    delete_google_event,
    sync_google_calendar,
    upsert_google_event
)
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest

from backend.ai import ask_gigachat, auto_assign_category

CLIENT_SECRETS_FILE = os.path.join("secrets", "client_secret.json")
SCOPES = ["https://www.googleapis.com/auth/calendar",
          "https://www.googleapis.com/auth/calendar.events"]
REDIRECT_URI = os.getenv("REDIRECT_URI", "https://pomnyasha.ru/api/oauth2/callback")

app = FastAPI(title="Помняша Backend")

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://pomnyasha.ru",
    "https://www.pomnyasha.ru"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Session-Id"],
)

pending_proposals: dict = {}

def _parse_dt(val: str) -> datetime:
    if val.endswith("Z"):
        val = val.replace("Z", "+00:00")
    dt = dtparser.parse(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt

def _get_or_create_session(request: Request) -> tuple[int, bool]:
    telegram_user_id = request.headers.get("x-telegram-user-id")
    if telegram_user_id and telegram_user_id.isdigit():
        return int(telegram_user_id), False
    
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

        redirect_url = os.getenv("FRONTEND_URL", "https://pomnyasha.ru")
        resp = RedirectResponse(redirect_url)
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
    ensure_user_exists(user_id)
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
        ensure_user_exists(user_id)
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
            source="local",
            view=auto_assign_category(title, description)
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
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        date_str = data.get("date")
        description = data.get("description", "")
        priority = data.get("priority", "medium")
        exclude_times = data.get("exclude_times", [])

        if not date_str:
            return JSONResponse({"error": "missing date"}, status_code=400)

        from datetime import datetime as _dt
        target_date = _dt.fromisoformat(date_str).date()

        existing_events = db.query(Event).filter(
            Event.user_id == user_id,
            Event.start_time >= datetime.combine(target_date, datetime.min.time()),
            Event.start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
        ).all()

        from backend.ai import suggest_optimal_time_with_exclusions
        suggested_time = suggest_optimal_time_with_exclusions(
            target_date,
            description,
            existing_events,
            priority,
            exclude_times
        )

        if suggested_time:
            time_str = suggested_time.strftime("%H:%M")
            return {
                "time": time_str,
                "message": f"Предлагаю время {time_str} - это оптимальный слот с учетом всех ваших задач на этот день."
            }
        else:
            return JSONResponse({"error": "Нет свободного времени на эту дату"}, status_code=400)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/stats")
def get_stats(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(response, user_id)

        events = db.query(Event).filter(Event.user_id == user_id).all()

        day_names = ['ПОНЕДЕЛЬНИК', 'ВТОРНИК', 'СРЕДА', 'ЧЕТВЕРГ', 'ПЯТНИЦА', 'СУББОТА', 'ВОСКРЕСЕНЬЕ']
        day_stats = {i: 0 for i in range(7)}

        for event in events:
            day_of_week = event.start_time.weekday()
            day_stats[day_of_week] += 1

        weekly_stats = []
        max_tasks = max(day_stats.values()) if day_stats else 0

        for i, day_name in enumerate(day_names):
            tasks_count = day_stats[i]
            weekly_stats.append({
                'day': day_name,
                'tasks': tasks_count,
                'isMostBusy': tasks_count == max_tasks and tasks_count > 0
            })

        category_stats = {}
        total_events = len(events)

        for event in events:

            category = getattr(event, 'view', None) or 'Личное'

            if not category or category == '':
                category = auto_assign_category(event.title or '', event.description or '')

                try:
                    event.view = category
                except Exception:
                    pass

            category_stats[category] = category_stats.get(category, 0) + 1

        if total_events > 0:
            pie_data = []
            colors = ['

            try:
                db.commit()
            except Exception:
                db.rollback()

            color_index = 0

            sorted_categories = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)

            for category, count in sorted_categories:
                if count > 0:
                    percentage = round((count / total_events) * 100)
                    pie_data.append({
                        'name': category,
                        'value': percentage,
                        'color': colors[color_index % len(colors)]
                    })
                    color_index += 1
        else:
            pie_data = []

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


@app.post("/chat")
def chat_endpoint(data: Dict[str, Any], request: Request, response: Response, db: Session = Depends(get_db)):
    msg = data.get("message", "")

    user_id, _ = _get_or_create_session(request)
    ensure_user_exists(user_id)
    _persist_session(response, user_id)

    try:
        events_without_category = db.query(Event).filter(
            Event.user_id == user_id,
            (Event.view.is_(None) | (Event.view == ""))
        ).limit(10).all()

        for event in events_without_category:
            category = auto_assign_category(
                event.title or "",
                event.description or ""
            )
            event.view = category

        if events_without_category:
            db.commit()
    except Exception:

        db.rollback()

    short_accepts = {'да', 'давай', 'ок', 'окей', 'хорошо', 'согласен', 'согласна'}
    msg_norm = (msg or '').strip().lower()

    try:
        schedule_markers = ["планы", "расписание", "дела", "задачи"]
        if any(word in msg_norm for word in schedule_markers):
            from datetime import date as _date

            target_date = _date.today()
            if "завтра" in msg_norm:
                target_date = target_date + timedelta(days=1)
            elif "послезавтра" in msg_norm:
                target_date = target_date + timedelta(days=2)
            else:

                import re as _re

                m = _re.search(r"(\\d{1,2})[.](\\d{1,2})(?:[.](\\d{2,4}))?", msg_norm)
                if m:
                    day, month = int(m.group(1)), int(m.group(2))
                    year = int(m.group(3)) if m.group(3) else target_date.year
                    if year < 100:
                        year += 2000
                    try:
                        target_date = _date(year, month, day)
                    except Exception:
                        pass

            start_dt = datetime.combine(target_date, datetime.min.time())
            end_dt = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

            day_events = (
                db.query(Event)
                .filter(Event.user_id == user_id, Event.start_time >= start_dt, Event.start_time < end_dt)
                .order_by(Event.start_time)
                .all()
            )

            if not day_events:
                text = f"На {target_date.strftime('%d.%m.%Y')} у тебя пока нет запланированных событий."
            else:
                parts = []
                for ev in day_events:
                    t = ev.start_time.strftime("%H:%M")
                    label = f" ({ev.view})" if getattr(ev, 'view', None) else ""
                    parts.append(f"{t} — {ev.title}{label}")
                text = (
                    f"На {target_date.strftime('%d.%m.%Y')} у тебя {len(day_events)} событ."
                    f"\n" + "\n".join(parts)
                )

            return {"reply": {"type": "text", "content": text}}
    except Exception:

        pass

    resp = {}

    if msg_norm in short_accepts:
        sid, created = _get_or_create_session(request)

        proposal = pending_proposals.get(sid)
        if proposal and isinstance(proposal, dict):

            try:

                processed = proposal.get('processed_task') or proposal
                date_str = processed.get('date')
                time_str = processed.get('time')
                title = processed.get('title') or processed.get('description') or 'Задача'

                if not date_str:
                    return {"reply": {"type": "text", "content": "Не удалось определить дату для события."}}

                if not time_str:

                    time_str = None

                if time_str:
                    event_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")
                else:
                    from backend.ai import suggest_optimal_time

                    target_date = datetime.fromisoformat(date_str).date()
                    existing_events = db.query(Event).filter(
                        Event.user_id == user_id,
                        Event.start_time >= datetime.combine(target_date, datetime.min.time()),
                        Event.start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
                    ).all()

                    suggested_time = suggest_optimal_time(
                        target_date,
                        title,
                        existing_events,
                        processed.get("priority", "medium"),
                    )

                    if suggested_time:
                        event_datetime = suggested_time
                    else:

                        event_datetime = datetime.fromisoformat(f"{date_str}T15:00")

                new_event = Event(
                    user_id=user_id,
                    title=title,
                    description=processed.get('description') or title,
                    start_time=event_datetime,
                    end_time=event_datetime,
                    source="ai_assistant",
                    view=processed.get('category') or auto_assign_category(title, processed.get('description') or "")
                )

                db.add(new_event)
                db.commit()
                db.refresh(new_event)

                try:
                    gid = upsert_google_event(user_id, new_event)
                    if gid:
                        new_event.external_id = gid
                        new_event.source = "google"
                        db.commit()
                except Exception as e:
                    print(f"Ошибка создания события в Google Calendar: {e}")

                try:
                    sync_google_calendar(user_id)
                except Exception as e:
                    print(f"Ошибка синхронизации с Google Calendar: {e}")

                try:
                    del pending_proposals[sid]
                except Exception:
                    pass

                return {"reply": {"type": "text", "content": f"✅ Событие '{title}' добавлено на {event_datetime.strftime('%d.%m.%Y %H:%M')}", "event_id": new_event.id}}
            except Exception as e:
                return {"reply": {"type": "text", "content": f"Ошибка при создании события: {e}"}}

    result = ask_gigachat(msg, db_session=db, user_id=user_id)

    try:
        if isinstance(result, dict) and result.get('type') == 'proposal' and result.get('needs_confirmation'):
            sid, _ = _get_or_create_session(request)
            pending_proposals[sid] = result
    except Exception:
        pass

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

@app.post('/auto-assign-categories')
def auto_assign_categories(request: Request, db: Session = Depends(get_db)):
    try:
        user_id, _ = _get_or_create_session(request)
        _persist_session(Response(), user_id)

        events_without_category = db.query(Event).filter(
            Event.user_id == user_id,
            (Event.view.is_(None) | (Event.view == ""))
        ).all()

        updated_count = 0
        categories_assigned = {}

        for event in events_without_category:

            category = auto_assign_category(
                event.title or "",
                event.description or ""
            )

            event.view = category
            updated_count += 1

            categories_assigned[category] = categories_assigned.get(category, 0) + 1

        db.commit()

        return {
            "success": True,
            "message": f"Автоматически присвоено категорий: {updated_count} задач",
            "updated_count": updated_count,
            "categories_assigned": categories_assigned
        }

    except Exception as e:
        db.rollback()
        return JSONResponse({"error": f"auto_assign_categories failed: {e}"}, status_code=500)


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

        try:
            event_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")
        except ValueError:
            return {"success": False, "message": "Неверный формат даты или времени"}

        category = auto_assign_category(description, description)

        new_event = Event(
            user_id=user_id,
            title=description,
            description=description,
            start_time=event_datetime,
            end_time=event_datetime,
            source="ai_assistant",
            view=category
        )

        db.add(new_event)
        db.commit()
        db.refresh(new_event)

        try:
            gid = upsert_google_event(user_id, new_event)
            if gid:
                new_event.external_id = gid
                new_event.source = "google"
                db.commit()
        except Exception as e:
            print(f"Ошибка создания события в Google Calendar: {e}")

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
