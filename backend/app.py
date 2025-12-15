import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any
from dateutil import parser as dtparser

from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db, create_tables, Event, get_user_creds, save_user_creds
from google_calendar import (
    create_google_event,
    delete_google_event,
    sync_google_calendar,
    upsert_google_event
)
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleRequest

from ai import ask_gigachat


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
        "source": e.source
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


@app.post("/chat")
def chat_endpoint(data: Dict[str, Any], request: Request, db: Session = Depends(get_db)):
    msg = data.get("message", "")

    # Получаем пользователя из сессии
    user_id, _ = _get_or_create_session(request)

    # Вызываем улучшенную версию ask_gigachat
    result = ask_gigachat(msg, db_session=db, user_id=user_id)

    return {"reply": result}


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
