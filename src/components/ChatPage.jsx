import React, { useState, useRef, useEffect } from 'react';
import './ChatPage.css';

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
    const response = await fetch(`${API_URL}/chat`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    return data.reply;
  };

  const confirmEventCreation = async (eventData) => {
    try {
      const response = await fetch(`${API_URL}/confirm-event`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
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

      if (botResponse.type === 'event_suggestion') {
        // Специальный формат для предложения события
        const eventData = botResponse.data;
        const suggestedTime = new Date(eventData.suggested_time);

        botMsg = {
          id: Date.now() + 1,
          text: `Предлагаю добавить событие "${eventData.description}" на ${eventData.date.toLocaleDateString('ru-RU')} в ${suggestedTime.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})}.\n\nСвободных слотов на эту дату: ${eventData.free_slots_count}`,
          isUser: false,
          timestamp: new Date(),
          eventSuggestion: {
            date: eventData.date,
            time: suggestedTime.toISOString().split('T')[1].slice(0, 5), // HH:MM format
            description: eventData.description,
            suggestedTime: suggestedTime
          }
        };
      } else {
        // Обычный текстовый ответ
        botMsg = {
          id: Date.now() + 1,
          text: botResponse.content || botResponse,
          isUser: false,
          timestamp: new Date()
        };
      }

      setMessages(prev => [...prev, botMsg]);
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
          ? { ...msg, eventSuggestion: null } // Убираем кнопки после ответа
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
        ? { ...msg, eventSuggestion: null } // Убираем кнопки
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
                    📆 {new Date(m.eventSuggestion.date).toLocaleDateString('ru-RU')}<br/>
                    🕐 {m.eventSuggestion.suggestedTime.toLocaleTimeString('ru-RU', {hour: '2-digit', minute: '2-digit'})}
                  </div>
                  <div className="event-actions">
                    <button
                      className="confirm-btn"
                      onClick={() => handleConfirmEvent(m.id, {
                        date: m.eventSuggestion.date.split('T')[0], // YYYY-MM-DD
                        time: m.eventSuggestion.time, // HH:MM
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
                  </div>
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