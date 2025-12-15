from datetime import datetime, timedelta
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session
from sqlalchemy import select

from database import engine, Event, get_user_creds

TIMEZONE = "Europe/Moscow"


def _service(user_id: int):
    creds = get_user_creds(user_id)
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds)


def create_google_event(user_id: int, event_data: dict) -> Optional[str]:
    svc = _service(user_id)
    if not svc:
        return None

    body = {
        "summary": event_data.get("title") or "Без названия",
        "description": event_data.get("description", ""),
        "start": {"dateTime": event_data["start"], "timeZone": TIMEZONE},
        "end": {"dateTime": event_data["end"], "timeZone": TIMEZONE},
    }

    try:
        created = svc.events().insert(calendarId="primary", body=body).execute()
        return created.get("id")
    except Exception:
        return None


def _update_google_event_raw(user_id: int, event_id: str, body: dict) -> bool:
    svc = _service(user_id)
    if not svc:
        return False
    try:
        svc.events().update(calendarId="primary", eventId=event_id, body=body).execute()
        return True
    except HttpError as e:
        if e.resp is not None and e.resp.status == 404:
            return False
        raise


def upsert_google_event(user_id: int, event: Event) -> Optional[str]:
    svc = _service(user_id)
    if not svc:
        return None

    body = {
        "summary": event.title,
        "description": event.description or "",
        "start": {"dateTime": event.start_time.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": event.end_time.isoformat(), "timeZone": TIMEZONE},
    }

    if event.external_id:
        ok = _update_google_event_raw(user_id, event.external_id, body)
        if ok:
            return None

    return create_google_event(
        user_id,
        {
            "title": event.title,
            "description": event.description or "",
            "start": event.start_time.isoformat(),
            "end": event.end_time.isoformat(),
        }
    )


def delete_google_event(user_id: int, event: Event):
    svc = _service(user_id)
    if not svc or not event.external_id:
        return
    try:
        svc.events().delete(calendarId="primary", eventId=event.external_id).execute()
    except HttpError:
        pass


def _fetch_google_events_window(user_id: int) -> list[dict]:
    svc = _service(user_id)
    if not svc:
        return []

    time_min = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
    time_max = (datetime.utcnow() + timedelta(days=90)).isoformat() + "Z"

    response = svc.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        showDeleted=True,
        orderBy="updated",
        maxResults=250,
    ).execute()

    return response.get("items", [])


def _dt_from_google(val: str) -> datetime:
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


def sync_google_calendar(user_id: int):
    svc = _service(user_id)
    if not svc:
        print("[sync] пользователь не авторизован Google")
        return

    db = Session(engine)
    try:
        google_events = _fetch_google_events_window(user_id)
        google_ids = set()

        for ge in google_events:
            gid = ge["id"]
            google_ids.add(gid)

            title = ge.get("summary", "Без названия")
            desc = ge.get("description") or ""
            start = ge.get("start", {}).get("dateTime")
            end = ge.get("end", {}).get("dateTime")
            deleted = ge.get("status") == "cancelled"

            local = db.scalar(
                select(Event).where(Event.external_id == gid, Event.user_id == user_id)
            )

            if deleted:
                if local:
                    db.delete(local)
                continue

            if not start or not end:
                continue

            start_dt = _dt_from_google(start)
            end_dt = _dt_from_google(end)

            if not local:
                db.add(Event(
                    user_id=user_id,
                    title=title,
                    description=desc,
                    start_time=start_dt,
                    end_time=end_dt,
                    external_id=gid,
                    source="google"
                ))
            else:
                changed = False
                if local.title != title:
                    local.title = title
                    changed = True
                if (local.description or "") != desc:
                    local.description = desc
                    changed = True
                if local.start_time != start_dt or local.end_time != end_dt:
                    local.start_time = start_dt
                    local.end_time = end_dt
                    changed = True

                if changed:
                    db.add(local)

        local_events = db.scalars(
            select(Event).where(
                Event.user_id == user_id,
                Event.external_id.is_not(None)
            )
        ).all()

        for e in local_events:
            if e.external_id not in google_ids:
                db.delete(e)

        db.commit()
        print("[sync] Google sync OK")

    except Exception as e:
        db.rollback()
        print("[sync] ошибка синхронизации:", e)

    finally:
        db.close()
