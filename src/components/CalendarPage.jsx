import React, { useState, useEffect, useCallback } from 'react';
import './CalendarPage.css';
import { fetchWithSession } from '../utils/session';

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

const CalendarPage = ({ onBack, onTaskUpdate }) => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [events, setEvents] = useState([]);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [isGoogleConnected, setIsGoogleConnected] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const apiFetch = useCallback((path, options = {}) => {
    return fetchWithSession(`${API_URL}${path}`, options);
  }, []);

  const loadEvents = useCallback(async () => {
    try {
      const response = await apiFetch('/events');
      const data = await response.json();
      setEvents(data);
    } catch (err) {
      console.error("Ошибка загрузки событий:", err);
    }
  }, [apiFetch]);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  const checkGoogleStatus = useCallback(async () => {
    try {
      const response = await apiFetch('/me');
      const data = await response.json();
      setIsGoogleConnected(Boolean(data.authorized));
    } catch (error) {
      console.error("Ошибка проверки Google состояния:", error);
      setIsGoogleConnected(false);
    }
  }, [apiFetch]);

  const synchronizeEvents = useCallback(async () => {
    if (!isGoogleConnected) {
      await loadEvents();
      return;
    }

    setIsSyncing(true);
    try {
      await apiFetch('/sync');
      await loadEvents();
    } catch (error) {
      console.error("Ошибка синхронизации:", error);
    } finally {
      setIsSyncing(false);
    }
  }, [apiFetch, isGoogleConnected, loadEvents]);

  useEffect(() => {
    checkGoogleStatus();
  }, [checkGoogleStatus]);

  useEffect(() => {
    synchronizeEvents();
  }, [synchronizeEvents]);

  useEffect(() => {
    const interval = setInterval(() => {
      checkGoogleStatus();
      synchronizeEvents();
    }, 60000);

    return () => clearInterval(interval);
  }, [checkGoogleStatus, synchronizeEvents]);

  const handleDeleteEvent = async (eventId) => {
    if (!window.confirm("Удалить событие?")) return;

    await apiFetch(`/events/${eventId}`, {
      method: "DELETE",
    });

    await synchronizeEvents();
    onTaskUpdate?.();
  };

  const getDaysInMonth = () => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();

    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);

    const days = [];
    for (let i = 0; i < firstDay.getDay(); i++) days.push(null);

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

  const dayNames = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

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
                  window.location.href = `${API_URL}/oauth2/login`;
                }
              }}
            >
              {isGoogleConnected ? 'Подключено' : 'Войти через Google'}
            </button>
            {isGoogleConnected && (
              <button
                className="sync-manual-btn"
                onClick={synchronizeEvents}
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
          <button className="calendar-nav-btn" onClick={() =>
            setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1))
          }>←</button>

          <div className="calendar-current-month">
            <h2>{monthNames[currentDate.getMonth()]} {currentDate.getFullYear()}</h2>
            <button className="today-btn" onClick={() => {
              setCurrentDate(new Date());
              setSelectedDate(new Date());
            }}>Сегодня</button>
          </div>

          <button className="calendar-nav-btn" onClick={() =>
            setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1))
          }>→</button>
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
                            {ev.title}
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
