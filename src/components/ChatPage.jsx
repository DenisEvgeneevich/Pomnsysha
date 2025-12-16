import React, { useState, useRef, useEffect } from 'react';
import './ChatPage.css';
import { getTelegramHeaders } from '../utils/telegramWebApp';

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

const ChatPage = ({ onBack }) => {
  const [messages, setMessages] = useState([
    {
      id: 1,
      text: "Привет! Я Помняша, ИИ-ассистент для планирования.\nПиши свои задачи — помогу всё разложить по времени!",
      isUser: false,
      timestamp: new Date()
    }
  ]);

  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessageToAPI = async (text) => {
    const telegramHeaders = getTelegramHeaders();
    const response = await fetch(`${API_URL}/chat`, {
      method: "POST",
      credentials: "include",
      headers: { 
        "Content-Type": "application/json",
        ...telegramHeaders
      },
      body: JSON.stringify({ message: text })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();

    return data.reply ?? data;
  };

  const confirmEventCreation = async (eventData) => {
    try {
      const telegramHeaders = getTelegramHeaders();
      const response = await fetch(`${API_URL}/confirm-event`, {
        method: "POST",
        credentials: "include",
        headers: { 
          "Content-Type": "application/json",
          ...telegramHeaders
        },
        body: JSON.stringify(eventData)
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      throw new Error(`Ошибка создания события: ${error.message}`);
    }
  };

  const formatDateLocal = (d) => {
    try {
      const dt = new Date(d);
      const y = dt.getFullYear();
      const m = String(dt.getMonth() + 1).padStart(2, '0');
      const day = String(dt.getDate()).padStart(2, '0');
      return `${y}-${m}-${day}`;
    } catch (e) {
      return d;
    }
  };

  const formatTimeLocal = (d) => {
    try {
      const dt = new Date(d);
      const hh = String(dt.getHours()).padStart(2, '0');
      const mm = String(dt.getMinutes()).padStart(2, '0');
      return `${hh}:${mm}`;
    } catch (e) {
      return d;
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || isLoading) return;

    const userMsg = {
      id: Date.now(),
      text: inputMessage,
      isUser: true,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMsg]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const botResponse = await sendMessageToAPI(inputMessage);

      let botMsg;

      const respType = (botResponse && typeof botResponse === 'object' && botResponse.type) || (typeof botResponse === 'string' ? 'text' : 'text');
      const respContent = (botResponse && typeof botResponse === 'object')
        ? (botResponse.content ?? botResponse.reply ?? botResponse.text ?? JSON.stringify(botResponse))
        : botResponse;

      if (respType === 'proposal' && botResponse.structured && botResponse.structured.processed_task) {
        const processed = botResponse.structured.processed_task;
        const dateStr = processed.date;
        const timeStr = processed.time || botResponse.suggested_time || null;
        const title = processed.title || processed.description || 'Задача';
        const category = processed.category || 'Личное';

        botMsg = {
          id: Date.now() + 1,
          text: botResponse.content || `Предлагаю добавить: "${title}" на ${dateStr} ${timeStr || 'время не указано'}. Категория: ${category}`,
          isUser: false,
          timestamp: new Date(),
          eventSuggestion: {
            date: dateStr,
            time: timeStr,
            description: title,
            category: category,
            suggestedTime: timeStr || null,
            showOtherTimeInput: false,
            otherTimeValue: ''
          }
        };
      } else if (respType === 'event_suggestion' || respType === 'event' || (botResponse && botResponse.data && botResponse.data.suggested_time)) {
        const eventData = (botResponse && botResponse.data) || {};
        const dateVal = eventData.date ? (typeof eventData.date === 'string' ? new Date(eventData.date) : eventData.date) : null;
        const suggested = eventData.suggested_time ? (typeof eventData.suggested_time === 'string' ? new Date(eventData.suggested_time) : eventData.suggested_time) : null;

        const dateDisplay = dateVal ? dateVal.toLocaleDateString('ru-RU') : (eventData.date || '');
        const suggestedTimeDisplay = suggested ? suggested.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'}) : (eventData.suggested_time || '');

        botMsg = {
          id: Date.now() + 1,
          text: `Предлагаю добавить событие "${eventData.description ?? eventData.title ?? respContent}" на ${dateDisplay} в ${suggestedTimeDisplay}.\n\nСвободных слотов на эту дату: ${eventData.free_slots_count ?? ''}`,
          isUser: false,
          timestamp: new Date(),
          eventSuggestion: {
            date: eventData.date ?? (dateVal ? formatDateLocal(dateVal) : null),
            time: suggested ? formatTimeLocal(suggested) : (typeof eventData.suggested_time === 'string' ? eventData.suggested_time : null),
            description: eventData.description ?? eventData.title ?? respContent,
            suggestedTime: suggested || null,
            showOtherTimeInput: false,
            otherTimeValue: ''
          }
        };
      } else {
        botMsg = {
          id: Date.now() + 1,
          text: typeof respContent === 'string' ? respContent : JSON.stringify(respContent),
          isUser: false,
          timestamp: new Date()
        };
      }

      setMessages(prev => [...prev, botMsg]);

      try {
        const assignments = (botResponse && (botResponse.assignments || (botResponse.structured && botResponse.structured.assignments))) || null;
        if (assignments && typeof assignments === 'object') {
          const telegramHeaders = getTelegramHeaders();
          fetch(`${API_URL}/assignments`, {
            method: 'POST',
            credentials: 'include',
            headers: { 
              'Content-Type': 'application/json',
              ...telegramHeaders
            },
            body: JSON.stringify({ assignments })
          }).catch(() => null);
        }
      } catch (e) {

      }
    } catch (error) {
      const errMsg = {
        id: Date.now() + 1,
        text: "⚠ Ошибка соединения с сервером.",
        isUser: false,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(e);
    }
  };

  const handleConfirmEvent = async (messageId, eventData) => {
    setIsLoading(true);

    try {
      const result = await confirmEventCreation(eventData);

      const confirmMsg = {
        id: Date.now() + 2,
        text: result.success
          ? `✅ ${result.message}`
          : `❌ ${result.message}`,
        isUser: false,
        timestamp: new Date()
      };

      setMessages(prev => prev.map(msg =>
        msg.id === messageId
          ? { ...msg, eventSuggestion: null }
          : msg
      ));

      setMessages(prev => [...prev, confirmMsg]);
    } catch (error) {
      const errorMsg = {
        id: Date.now() + 2,
        text: `❌ ${error.message}`,
        isUser: false,
        timestamp: new Date()
      };

      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancelEvent = (messageId) => {
    const cancelMsg = {
      id: Date.now() + 2,
      text: "Отменено. Можете попробовать другое время или дату.",
      isUser: false,
      timestamp: new Date()
    };

    setMessages(prev => prev.map(msg =>
      msg.id === messageId
        ? { ...msg, eventSuggestion: null }
        : msg
    ));

    setMessages(prev => [...prev, cancelMsg]);
  };

  return (
    <div className="chat-page">
      <header className="chat-header">
        <button className="back-button" onClick={onBack}>← Назад</button>
        <h1>Чат с Помняшей</h1>
      </header>

      <div className="chat-messages">
        {messages.map(m => (
          <div key={m.id} className={`message ${m.isUser ? 'user-message' : 'bot-message'}`}>
            <div className="message-content">
              {m.text.split('\n').map((line, i) => <p key={i}>{line}</p>)}
              {m.eventSuggestion && (
                <div className="event-confirmation">
                  <div className="event-details">
                    <strong>📅 {m.eventSuggestion.description}</strong><br/>
                    📆 {m.eventSuggestion.date ? new Date(m.eventSuggestion.date).toLocaleDateString('ru-RU') : ''}<br/>
                    🕐 {m.eventSuggestion.time}
                  </div>
                  <div className="event-actions">
                    <button
                      className="confirm-btn"
                      onClick={() => handleConfirmEvent(m.id, {
                        date: (m.eventSuggestion.date && m.eventSuggestion.date.split ? m.eventSuggestion.date.split('T')[0] : m.eventSuggestion.date) || m.eventSuggestion.date,
                        time: m.eventSuggestion.time,
                        description: m.eventSuggestion.description
                      })}
                      disabled={isLoading}
                    >
                      ✅ Подтвердить
                    </button>
                    <button
                      className="cancel-btn"
                      onClick={() => handleCancelEvent(m.id)}
                      disabled={isLoading}
                    >
                      ❌ Отмена
                    </button>
                    <button
                      className="other-time-btn"
                      onClick={async () => {
                        setIsLoading(true);
                        try {

                          const excludeTimes = [];
                          if (m.eventSuggestion.time) {
                            excludeTimes.push(m.eventSuggestion.time);
                          }
                          if (m.eventSuggestion.previousTimes) {
                            excludeTimes.push(...m.eventSuggestion.previousTimes);
                          }

                          const res = await fetch(`${API_URL}/suggest-times`, {
                            method: 'POST',
                            credentials: 'include',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              date: m.eventSuggestion.date && m.eventSuggestion.date.split ? m.eventSuggestion.date.split('T')[0] : m.eventSuggestion.date,
                              description: m.eventSuggestion.description,
                              priority: 'medium',
                              exclude_times: excludeTimes
                            })
                          });

                          if (!res.ok) {
                            const errorData = await res.json();
                            throw new Error(errorData.error || 'Ошибка получения времени');
                          }

                          const body = await res.json();
                          const newTime = body.time;
                          const message = body.message || `Предлагаю новое время: ${newTime}`;

                          if (newTime) {

                            const previousTimes = [
                              ...(m.eventSuggestion.previousTimes || []),
                              ...(m.eventSuggestion.time ? [m.eventSuggestion.time] : [])
                            ];

                            setMessages(prev => prev.map(msg =>
                              msg.id === m.id
                                ? {
                                    ...msg,
                                    eventSuggestion: {
                                      ...msg.eventSuggestion,
                                      time: newTime,
                                      previousTimes: previousTimes,
                                      newTimeProposed: true,
                                      newTimeMessage: message
                                    }
                                  }
                                : msg
                            ));
                          }
                        } catch (e) {

                          const errorMsg = {
                            id: Date.now() + 1000,
                            text: `⚠ ${e.message || 'Не удалось получить новое время'}`,
                            isUser: false,
                            timestamp: new Date()
                          };
                          setMessages(prev => [...prev, errorMsg]);
                        } finally {
                          setIsLoading(false);
                        }
                      }}
                      disabled={isLoading}
                    >
                      🕘 Другое время
                    </button>
                  </div>
                  {m.eventSuggestion.newTimeProposed && m.eventSuggestion.newTimeMessage && (
                    <div className="new-time-proposal">
                      <div className="new-time-message">{m.eventSuggestion.newTimeMessage}</div>
                      <div className="new-time-display">
                        Новое время: <strong>{m.eventSuggestion.time}</strong>
                      </div>
                      <button
                        className="confirm-new-time-btn"
                        onClick={() => handleConfirmEvent(m.id, {
                          date: (m.eventSuggestion.date && m.eventSuggestion.date.split ? m.eventSuggestion.date.split('T')[0] : m.eventSuggestion.date) || m.eventSuggestion.date,
                          time: m.eventSuggestion.time,
                          description: m.eventSuggestion.description
                        })}
                        disabled={isLoading}
                      >
                        ✅ Подтвердить новое время
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
            <span className="message-time">
              {m.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}

        {isLoading && (
          <div className="message bot-message">
            <div className="message-content loading">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-form" onSubmit={handleSendMessage}>
        <div className="input-container">
          <textarea
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="Введите сообщение..."
            onKeyPress={handleKeyPress}
            disabled={isLoading}
          />
          <button type="submit" disabled={!inputMessage.trim() || isLoading}>
            {isLoading ? "⏳" : "📨"}
          </button>
        </div>
      </form>
    </div>
  );
};

export default ChatPage;