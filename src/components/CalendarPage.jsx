import React, { useState, useEffect, useCallback } from 'react';
import './CalendarPage.css';
import { fetchWithSession } from '../utils/session';

// В проде по умолчанию работаем через nginx-прокси: /api -> backend
// Локально можно переопределить: REACT_APP_API_URL=http://localhost:8000
const API_URL = process.env.REACT_APP_API_URL || "/api";

const CalendarPage = ({ onBack, onTaskUpdate }) => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [events, setEvents] = useState([]);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [isGoogleConnected, setIsGoogleConnected] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const apiFetch = useCallback((path, options = {}) => {
    // path должен начинаться с /
    const url = `${API_URL}${path}`;
    return fetchWithSession(url, options);
  }, [API_URL]);

  const loadEvents = useCallback(async () => {
    try {
      const response = await apiFetch('/events');
      const data = await response.json();

      console.log("Загружены события:", (data || []).map(e => ({
        id: e.id,
        title: e.title,
        view: e.view
      })));

      setEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Ошибка загрузки событий:", err);
      setEvents([]);
    }
  }, [apiFetch]);

  const synchronizeEvents = useCallback(async () => {
    setIsSyncing(true);
    try {
      await apiFetch('/sync');
    } catch (error) {
      console.error("Ошибка синхронизации:", error);
    } finally {
      setIsSyncing(false);
    }
  }, [apiFetch]);

  const refreshAll = useCallback(async () => {
    // 1) статус Google
    let authorized = false;
    try {
      const response = await apiFetch('/me');
      const data = await response.json();
      authorized = Boolean(data?.authorized);
      setIsGoogleConnected(authorized);
    } catch (error) {
      console.error("Ошибка проверки Google состояния:", error);
      setIsGoogleConnected(false);
      authorized = false;
    }

    // 2) если подключено — синк
    if (authorized) {
      await synchronizeEvents();
    }

    // 3) всегда перечитываем события
    await loadEvents();
  }, [apiFetch, loadEvents, synchronizeEvents]);

  // Первичная загрузка
  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  // Если вернулись с OAuth — форсим refresh и чистим URL
  useEffect(() => {
    const url = new URL(window.location.href);

    const hasOAuthReturn =
      url.searchParams.has("code") ||
      url.searchParams.has("state");

    if (hasOAuthReturn) {
      refreshAll().finally(() => {
        url.searchParams.delete("code");
        url.searchParams.delete("state");
        url.searchParams.delete("scope");
        url.searchParams.delete("authuser");
        url.searchParams.delete("prompt");

        window.history.replaceState(
          {},
          "",
          url.pathname + (url.searchParams.toString() ? `?${url.searchParams.toString()}` : "")
        );
      });
    }
  }, [refreshAll]);

  // Периодический авто-рефреш раз в минуту
  useEffect(() => {
    const interval = setInterval(() => {
      refreshAll();
    }, 60000);

    return () => clearInterval(interval);
  }, [refreshAll]);

  const handleDeleteEvent = async (eventId) => {
    if (!window.confirm("Удалить событие?")) return;

    try {
      await apiFetch(`/events/${eventId}`, { method: "DELETE" });
    } catch (e) {
      console.error("Ошибка удаления:", e);
    }

    await refreshAll();
    onTaskUpdate?.();
  };

  const getDaysInMonth = () => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);

    const days = [];

    // Календарь начинается с понедельника:
    // JS: 0=вс,1=пн,...6=сб => делаем пн=0,...вс=6
    let firstDayOfWeek = firstDay.getDay();
    if (firstDayOfWeek === 0) firstDayOfWeek = 6;
    else firstDayOfWeek = firstDayOfWeek - 1;

    for (let i = 0; i < firstDayOfWeek; i++) days.push(null);

    for (let d = 1; d <= lastDay.getDate(); d++) {
      const date = new Date(year, month, d);

      const dateEvents = events.filter(ev => {
        const evDate = new Date(ev.start);
        return evDate.toDateString() === date.toDateString();
      });

      days.push({ date, day: d, events: dateEvents });
    }

    return days;
  };

  const getSelectedEvents = () =>
    events.filter(ev => new Date(ev.start).toDateString() === selectedDate.toDateString());

  const days = getDaysInMonth();

  const monthNames = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
  ];

  const dayNames = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

  const selectedEvents = getSelectedEvents();

  return (
    <div className="calendar-page">
      <button className="calendar-back-btn" onClick={onBack}>← На главную</button>

      <div className="calendar-container">
        <div className="calendar-header">
          <h1 className="calendar-title">Календарь</h1>

          <div className="google-actions">
            <button
              className={`google-auth-btn ${isGoogleConnected ? 'connected' : ''}`}
              onClick={() => {
                if (!isGoogleConnected) {
                  // Важно: идём в backend через /api
                  window.location.href = `${API_URL}/oauth2/login`;
                }
              }}
            >
              {isGoogleConnected ? 'Подключено' : 'Войти через Google'}
            </button>

            {isGoogleConnected && (
              <button
                className="sync-manual-btn"
                onClick={refreshAll}
                disabled={isSyncing}
              >
                Обновить
              </button>
            )}

            {isGoogleConnected && (
              <div className={`sync-indicator ${isSyncing ? 'active' : ''}`}>
                Синхронизация
                <span className="dots">
                  <span>.</span>
                  <span>.</span>
                  <span>.</span>
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Навигация */}
        <div className="calendar-controls">
          <button
            className="calendar-nav-btn"
            onClick={() => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1))}
          >
            ←
          </button>

          <div className="calendar-current-month">
            <h2>{monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}</h2>
            <button
              className="today-btn"
              onClick={() => {
                setCurrentDate(new Date());
                setSelectedDate(new Date());
              }}
            >
              Сегодня
            </button>
          </div>

          <button
            className="calendar-nav-btn"
            onClick={() => setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1))}
          >
            →
          </button>
        </div>

        <div className="calendar-content">
          {/* Сетка */}
          <div className="calendar-grid">
            {dayNames.map(d => (
              <div key={d} className="calendar-day-header">{d}</div>
            ))}

            {days.map((item, i) => (
              <div
                key={i}
                className={`calendar-day 
                  ${item ? (item.date.toDateString() === selectedDate.toDateString() ? "selected" : "") : "empty"}
                  ${item && item.events.length > 0 ? "has-events" : ""}
                  ${item && item.date.toDateString() === new Date().toDateString() ? "today" : ""}
                `}
                onClick={() => item && setSelectedDate(item.date)}
              >
                {item && (
                  <>
                    <div className="calendar-day-number">{item.day}</div>
                    {item.events.length > 0 && (
                      <div className="calendar-day-events">
                        {item.events.slice(0, 3).map((ev, idx) => (
                          <div key={idx} className="calendar-event-preview">
                            <div className="event-preview-title">{ev.title}</div>
                            {ev.view && <div className="event-preview-category">{ev.view}</div>}
                          </div>
                        ))}
                        {item.events.length > 3 && (
                          <div className="calendar-more-events">
                            +{item.events.length - 3}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>

          {/* Правая панель */}
          <div className="calendar-events-panel">
            <h3>События на {selectedDate.toLocaleDateString("ru-RU")}</h3>

            {selectedEvents.length ? (
              selectedEvents.map(ev => (
                <div key={ev.id} className="calendar-event-item">
                  <div className="event-time">
                    {new Date(ev.start).toLocaleTimeString("ru-RU", {
                      hour: "2-digit",
                      minute: "2-digit"
                    })}
                    {ev.view && (
                      <div className="event-time-category">
                        {ev.view}
                      </div>
                    )}
                  </div>

                  <div className="event-details">
                    <div className="event-title">{ev.title}</div>
                    {ev.description && (
                      <div className="event-description">{ev.description}</div>
                    )}
                  </div>

                  <button className="delete-event-btn" onClick={() => handleDeleteEvent(ev.id)}>×</button>
                </div>
              ))
            ) : (
              <div className="no-events">На этот день событий нет</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CalendarPage;
