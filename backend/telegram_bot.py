import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from sqlalchemy.orm import Session
from backend.database import get_db, Event, get_user_creds, save_user_creds, ensure_user_exists
from backend.ai import ask_gigachat, auto_assign_category
from backend.google_calendar import sync_google_calendar, upsert_google_event
from backend.ai import suggest_optimal_time_with_exclusions

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8014523011:AAHxGI-hx8XaiVJ99hC2OYGz21g3euk1Df4")
if not TELEGRAM_BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN not set")

pending_proposals: Dict[int, Dict[str, Any]] = {}

def get_user_id_from_update(update: Update) -> int:
    return update.effective_user.id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я Помняша, ИИ-ассистент для планирования.\n"
        "Пиши свои задачи — помогу всё разложить по времени!\n\n"
        "Команды:\n"
        "/events - показать события\n"
        "/stats - статистика\n"
        "/sync - синхронизировать с Google Calendar"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id_from_update(update)
    msg = update.message.text

    ensure_user_exists(user_id)
    db = next(get_db())
    try:
        events_without_category = db.query(Event).filter(
            Event.user_id == user_id,
            (Event.view.is_(None) | (Event.view == ""))
        ).limit(10).all()

        for event in events_without_category:
            category = auto_assign_category(event.title or "", event.description or "")
            event.view = category

        if events_without_category:
            db.commit()
    except Exception:
        db.rollback()

    msg_norm = (msg or '').strip().lower()
    short_accepts = {'да', 'давай', 'ок', 'окей', 'хорошо', 'согласен', 'согласна'}

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
                m = _re.search(r"(\d{1,2})[.](\d{1,2})(?:[.](\d{2,4}))?", msg_norm)
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

            day_events = db.query(Event).filter(
                Event.user_id == user_id,
                Event.start_time >= start_dt,
                Event.start_time < end_dt
            ).order_by(Event.start_time).all()

            if not day_events:
                text = f"На {target_date.strftime('%d.%m.%Y')} у тебя пока нет запланированных событий."
            else:
                parts = []
                for ev in day_events:
                    t = ev.start_time.strftime("%H:%M")
                    label = f" ({ev.view})" if getattr(ev, 'view', None) else ""
                    parts.append(f"{t} — {ev.title}{label}")
                text = f"На {target_date.strftime('%d.%m.%Y')} у тебя {len(day_events)} событ.\n" + "\n".join(parts)

            await update.message.reply_text(text)
            return
    except Exception:
        pass

    if msg_norm in short_accepts:
        proposal = pending_proposals.get(user_id)
        if proposal and isinstance(proposal, dict):
            try:
                processed = proposal.get('processed_task') or proposal
                date_str = processed.get('date')
                time_str = processed.get('time')
                title = processed.get('title') or processed.get('description') or 'Задача'

                if not date_str:
                    await update.message.reply_text("Не удалось определить дату для события.")
                    return

                ensure_user_exists(user_id)
                if not time_str:
                    from backend.ai import suggest_optimal_time
                    target_date = datetime.fromisoformat(date_str).date()
                    existing_events = db.query(Event).filter(
                        Event.user_id == user_id,
                        Event.start_time >= datetime.combine(target_date, datetime.min.time()),
                        Event.start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
                    ).all()

                    suggested_time = suggest_optimal_time(
                        target_date, title, existing_events, processed.get("priority", "medium")
                    )

                    if suggested_time:
                        event_datetime = suggested_time
                    else:
                        event_datetime = datetime.fromisoformat(f"{date_str}T15:00")
                else:
                    event_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")

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
                except Exception:
                    pass

                try:
                    sync_google_calendar(user_id)
                except Exception:
                    pass

                del pending_proposals[user_id]
                await update.message.reply_text(f"✅ Событие '{title}' добавлено на {event_datetime.strftime('%d.%m.%Y %H:%M')}")
                return
            except Exception as e:
                await update.message.reply_text(f"Ошибка при создании события: {e}")
                return

    result = ask_gigachat(msg, db_session=db, user_id=user_id)

    try:
        if isinstance(result, dict) and result.get('type') == 'proposal' and result.get('needs_confirmation'):
            pending_proposals[user_id] = result
    except Exception:
        pass

    if isinstance(result, dict):
        if result.get('type') == 'proposal':
            processed = result.get('structured', {}).get('processed_task', {})
            date_str = processed.get('date', '')
            time_str = processed.get('time') or result.get('suggested_time', '')
            title = processed.get('title', 'Задача')

            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}_{date_str}_{time_str}_{title}")],
                [InlineKeyboardButton("🕘 Другое время", callback_data=f"other_time_{user_id}_{date_str}_{title}")],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            text = result.get('content', f"Предлагаю добавить: '{title}' на {date_str} {time_str}")
            await update.message.reply_text(text, reply_markup=reply_markup)
        elif result.get('type') == 'text':
            await update.message.reply_text(result.get('content', 'Не удалось обработать запрос'))
        else:
            await update.message.reply_text(str(result))
    else:
        await update.message.reply_text(str(result))

    db.close()

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = get_user_id_from_update(update)

    if data.startswith("confirm_"):
        parts = data.split("_", 4)
        if len(parts) >= 5:
            _, _, date_str, time_str, title = parts
            ensure_user_exists(user_id)
            db = next(get_db())
            try:
                event_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")
                category = auto_assign_category(title, title)

                new_event = Event(
                    user_id=user_id,
                    title=title,
                    description=title,
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
                except Exception:
                    pass

                try:
                    sync_google_calendar(user_id)
                except Exception:
                    pass

                await query.edit_message_text(f"✅ Событие '{title}' добавлено на {event_datetime.strftime('%d.%m.%Y %H:%M')}")
            except Exception as e:
                await query.edit_message_text(f"Ошибка: {e}")
            finally:
                db.close()

    elif data.startswith("other_time_"):
        parts = data.split("_", 3)
        if len(parts) >= 4:
            _, _, date_str, title = parts
            ensure_user_exists(user_id)
            db = next(get_db())
            try:
                target_date = datetime.fromisoformat(date_str).date()
                existing_events = db.query(Event).filter(
                    Event.user_id == user_id,
                    Event.start_time >= datetime.combine(target_date, datetime.min.time()),
                    Event.start_time < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
                ).all()

                exclude_times = []
                if user_id in pending_proposals:
                    proposal = pending_proposals[user_id]
                    processed = proposal.get('processed_task', {})
                    if processed.get('time'):
                        exclude_times.append(processed.get('time'))

                suggested_time = suggest_optimal_time_with_exclusions(
                    target_date, title, existing_events, "medium", exclude_times
                )

                if suggested_time:
                    time_str = suggested_time.strftime("%H:%M")
                    keyboard = [
                        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{user_id}_{date_str}_{time_str}_{title}")],
                        [InlineKeyboardButton("🕘 Другое время", callback_data=f"other_time_{user_id}_{date_str}_{title}")],
                        [InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{user_id}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(f"Предлагаю время {time_str} для '{title}'", reply_markup=reply_markup)
                else:
                    await query.edit_message_text("Нет свободного времени на эту дату")
            except Exception as e:
                await query.edit_message_text(f"Ошибка: {e}")
            finally:
                db.close()

    elif data.startswith("cancel_"):
        if user_id in pending_proposals:
            del pending_proposals[user_id]
        await query.edit_message_text("Отменено")

async def show_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id_from_update(update)
    ensure_user_exists(user_id)
    db = next(get_db())
    try:
        events = db.query(Event).filter(Event.user_id == user_id).order_by(Event.start_time).limit(10).all()

        if not events:
            await update.message.reply_text("У тебя пока нет событий")
            return

        text = "Твои события:\n\n"
        for ev in events:
            date_str = ev.start_time.strftime("%d.%m.%Y")
            time_str = ev.start_time.strftime("%H:%M")
            label = f" [{ev.view}]" if getattr(ev, 'view', None) else ""
            text += f"{date_str} {time_str} — {ev.title}{label}\n"

        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        db.close()

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id_from_update(update)
    ensure_user_exists(user_id)
    db = next(get_db())
    try:
        events = db.query(Event).filter(Event.user_id == user_id).all()

        category_stats = {}
        day_stats = {i: 0 for i in range(7)}

        for event in events:
            category = getattr(event, 'view', None) or 'Личное'
            if not category or category == '':
                category = auto_assign_category(event.title or '', event.description or '')
                try:
                    event.view = category
                except Exception:
                    pass
            category_stats[category] = category_stats.get(category, 0) + 1
            day_stats[event.start_time.weekday()] += 1

        db.commit()

        day_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        text = f"Статистика ({len(events)} событий):\n\n"
        text += "По категориям:\n"
        for cat, count in sorted(category_stats.items(), key=lambda x: x[1], reverse=True):
            text += f"{cat}: {count}\n"

        text += "\nПо дням недели:\n"
        for i, day_name in enumerate(day_names):
            text += f"{day_name}: {day_stats[i]}\n"

        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        db.close()

async def sync_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = get_user_id_from_update(update)
    try:
        sync_google_calendar(user_id)
        await update.message.reply_text("✅ Синхронизация завершена")
    except Exception as e:
        await update.message.reply_text(f"Ошибка синхронизации: {e}")

def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set, bot will not start")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("events", show_events))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("sync", sync_calendar))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Telegram bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    run_bot()
