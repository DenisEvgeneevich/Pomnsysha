import React, { useState, useRef, useEffect, useCallback } from 'react';
import './ChatPage.css';
import { fetchWithSession } from '../utils/session';

const API_URL = (process.env.REACT_APP_API_URL ?? "/api").replace(/\/+$/, "");


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

  const apiFetch = useCallback((path, options = {}) => {
    return fetchWithSession(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessageToAPI = async (text) => {
    const response = await apiFetch(`/chat`, {
      method: "POST",
      credentials: "include",
      body: JSON.stringify({ message: text })
    });

    if (!response.ok) {
      const bodyText = await response.text().catch(() => "");
      throw new Error(`HTTP ${response.status}: ${bodyText || response.statusText}`);
    }

    const data = await response.json();
    // Возвращаем либо `reply`, либо сам объект ответа — это безопаснее
    return data.reply ?? data;
  };

  const confirmEventCreation = async (eventData) => {
    try {
      const response = await apiFetch(`/confirm-event`, {
        method: "POST",
        credentials: "include",
        body: JSON.stringify(eventData)
      });

      if (!response.ok) {
        const bodyText = await response.text().catch(() => "");
        throw new Error(`HTTP ${response.status}: ${bodyText || response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      throw new Error(`Ошибка создания события: ${error.message}`);
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
    const textToSend = inputMessage;
    setInputMessage('');
    setIsLoading(true);

    try {
      const botResponse = await sendMessageToAPI(textToSend);

      let botMsg;

      // Нормализуем ответ модели
      const respType =
        (botResponse && typeof botResponse === 'object' && botResponse.type) ||
        (typeof botResponse === 'string' ? 'text' : 'text');

      const respContent = (botResponse && typeof botResponse === 'object')
        ? (botResponse.content ?? botResponse.reply ?? botResponse.text ?? JSON.stringify(botResponse))
        : botResponse;

      // availability_result: только текст
      if (respType === 'availability_result' || (botResponse && botResponse.type === 'availability_result')) {
        const availData = botResponse;
        const slots = availData.slots || [];
        const message = availData.message || 'Свободные окна не найдены';
        const hintCommand = availData.hint_command || null;

        let fullText = message;
        if (slots.length > 0) {
          fullText += '\n\nДоступные окна:';
          slots.forEach((slot, idx) => {
            const date = new Date(slot.date).toLocaleDateString('ru-RU');
            fullText += `\n${idx + 1}. ${date} ${slot.start}–${slot.end}`;
          });
        }
        if (hintCommand) {
          fullText += `\n\n💡 ${hintCommand}`;
        }

        botMsg = {
          id: Date.now() + 1,
          text: fullText,
          isUser: false,
          timestamp: new Date()
        };
      } else if (respType === 'proposal' && botResponse.structured && botResponse.structured.processed_task) {
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
      } else if (respType === 'event_suggestion' || (botResponse && botResponse.type === 'event_suggestion')) {
        const eventData = botResponse;
        const title = eventData.title || 'Событие';
        const date = eventData.date || '';
        const start = eventData.start || '';
        const durationMin = eventData.duration_min || 60;
        const category = eventData.category || 'Личное';
        const idempotencyKey = eventData.idempotency_key || null;

        const dateDisplay = date ? new Date(date).toLocaleDateString('ru-RU') : '';

        botMsg = {
          id: Date.now() + 1,
          text: `Предлагаю добавить: "${title}" на ${dateDisplay} в ${start} (${durationMin} минут). Категория: ${category}`,
          isUser: false,
          timestamp: new Date(),
          eventSuggestion: {
            date: date,
            time: start,
            description: title,
            category: category,
            duration_min: durationMin,
            idempotency_key: idempotencyKey,
            suggestedTime: start,
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

      // assignments -> бек
      try {
        const assignments =
          (botResponse && (botResponse.assignments || (botResponse.structured && botResponse.structured.assignments))) || null;

        if (assignments && typeof assignments === 'object') {
          apiFetch(`/assignments`, {
            method: 'POST',
            credentials: 'include',
            body: JSON.stringify({ assignments })
          }).catch(() => null);
        }
      } catch (e) {
        // ignore
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
      const eventDataWithKey = {
        ...eventData,
        idempotency_key: eventData.idempotency_key || null,
        duration_min: eventData.duration_min || 60
      };
      const result = await confirmEventCreation(eventDataWithKey);

      const confirmMsg = {
        id: Date.now() + 2,
        text: result.success ? `✅ ${result.message}` : `❌ ${result.message}`,
        isUser: false,
        timestamp: new Date()
      };

      setMessages(prev => prev.map(msg =>
        msg.id === messageId ? { ...msg, eventSuggestion: null } : msg
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
      msg.id === messageId ? { ...msg, eventSuggestion: null } : msg
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
                    <strong>📅 {m.eventSuggestion.description}</strong><br />
                    📆 {m.eventSuggestion.date ? new Date(m.eventSuggestion.date).toLocaleDateString('ru-RU') : ''}<br />
                    🕐 {m.eventSuggestion.time}
                  </div>

                  <div className="event-actions">
                    <button
                      className="confirm-btn"
                      onClick={() => handleConfirmEvent(m.id, {
                        date: (m.eventSuggestion.date && m.eventSuggestion.date.split ? m.eventSuggestion.date.split('T')[0] : m.eventSuggestion.date) || m.eventSuggestion.date,
                        time: m.eventSuggestion.time,
                        description: m.eventSuggestion.description,
                        duration_min: m.eventSuggestion.duration_min || 60,
                        idempotency_key: m.eventSuggestion.idempotency_key || null
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
                          if (m.eventSuggestion.time) excludeTimes.push(m.eventSuggestion.time);
                          if (m.eventSuggestion.previousTimes) excludeTimes.push(...m.eventSuggestion.previousTimes);

                          const res = await apiFetch(`/suggest-times`, {
                            method: 'POST',
                            credentials: 'include',
                            body: JSON.stringify({
                              date: m.eventSuggestion.date && m.eventSuggestion.date.split ? m.eventSuggestion.date.split('T')[0] : m.eventSuggestion.date,
                              description: m.eventSuggestion.description,
                              priority: 'medium',
                              exclude_times: excludeTimes
                            })
                          });

                          if (!res.ok) {
                            const errorText = await res.text().catch(() => "");
                            throw new Error(errorText || 'Ошибка получения времени');
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
                          description: m.eventSuggestion.description,
                          duration_min: m.eventSuggestion.duration_min || 60,
                          idempotency_key: m.eventSuggestion.idempotency_key || null
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
