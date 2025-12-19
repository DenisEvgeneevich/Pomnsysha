import React, { useState, useEffect, useCallback } from 'react';
import CalendarModal from './components/CalendarModal';
import ChatPage from './components/ChatPage';
import StatisticsPage from './components/StatisticsPage';
import CalendarPage from './components/CalendarPage';
import icon1 from './icons/Calendar.png';
import icon2 from './icons/Pony.png';
import icon3 from './icons/Stats.png';
import './App.css';
import { fetchWithSession } from './utils/session';

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

const App = () => {
  const [currentPage, setCurrentPage] = useState('home');
  const [tasks, setTasks] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newTaskText, setNewTaskText] = useState('');
  const [tempTask, setTempTask] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const apiFetch = useCallback((path, options = {}) => {
    return fetchWithSession(`${API_URL}${path}`, options);
  }, []);

  const loadTasks = useCallback(async () => {
    try {
      const response = await apiFetch('/events');
      if (!response.ok) {
        console.error("Ошибка загрузки задач: HTTP", response.status);
        return;
      }
      const events = await response.json();
      const today = new Date().toDateString();

      const todayTasks = events
        .filter(ev => new Date(ev.start).toDateString() === today)
        .map(ev => ({
          id: ev.id,
          text: ev.title,
          completed: false
        }));

      setTasks(todayTasks);
    } catch (e) {
      console.error("Ошибка загрузки задач:", e);
      // Не показываем ошибку пользователю при загрузке, чтобы не мешать работе
    }
  }, [apiFetch]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  const handleAddTaskClick = () => {
    if (newTaskText.trim()) {
      setTempTask(newTaskText.trim());
      setIsModalOpen(true);
    }
  };

  const handleAddCalendarEvent = async ({ startTime, description }) => {
    setIsLoading(true);

    try {
      const response = await apiFetch('/events', {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: tempTask,
          description,
          start: startTime,
          end: startTime
        })
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error("Ошибка ответа backend:", errorText);
        alert(`Ошибка при добавлении задачи: ${errorText || 'Сервер не отвечает. Убедитесь, что backend запущен на порту 8000.'}`);
        return;
      }

      setNewTaskText('');
      setTempTask('');
      setIsModalOpen(false);

      await loadTasks();
    } catch (error) {
      console.error("Ошибка добавления:", error);
      alert(`Ошибка соединения с сервером: ${error.message}. Убедитесь, что backend запущен на http://localhost:8000`);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleTask = async (id) => {
    setIsLoading(true);

    try {
      await apiFetch(`/events/${id}`, {
        method: "DELETE",
      });

      await loadTasks();
    } catch (error) {
      console.error("Ошибка удаления:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') handleAddTaskClick();
  };

  if (currentPage === 'chat') {
    return (
      <div className="app-wrapper">
        <ChatPage onBack={() => setCurrentPage('home')} />
        <Footer setCurrentPage={setCurrentPage} />
      </div>
    );
  }

  if (currentPage === 'stats') {
    return (
      <div className="app-wrapper">
        <StatisticsPage onBack={() => setCurrentPage('home')} />
        <Footer setCurrentPage={setCurrentPage} />
      </div>
    );
  }

  if (currentPage === 'calendar') {
    return (
      <div className="app-wrapper">
        <CalendarPage
          onBack={() => setCurrentPage('home')}
          onTaskUpdate={loadTasks}
        />
        <Footer setCurrentPage={setCurrentPage} />
      </div>
    );
  }

  return (
    <div className="app-wrapper">
      <main className="main">
        <div className="container">
          <div className="main-todos">
            <h1 className="main-hello">Доброе утро!</h1>
            <h2 className="main-title">Твои планы на сегодня:</h2>

            {isLoading ? (
              <div style={{ textAlign: 'center', padding: '20px' }}>
                <p>Загрузка...</p>
              </div>
            ) : (
              <ul className="main-list">
                {tasks.map(task => (
                  <li key={task.id}>
                    <label>
                      <input
                        type="checkbox"
                        onChange={() => toggleTask(task.id)}
                        disabled={isLoading}
                      />
                      <span className="task-text">
                        {task.text} 📅
                      </span>
                    </label>
                  </li>
                ))}

                {tasks.length === 0 && (
                  <li style={{ textAlign: 'center', color: '#999' }}>
                    На сегодня задач нет
                  </li>
                )}
              </ul>
            )}

            <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
              <input
                type="text"
                value={newTaskText}
                onChange={(e) => setNewTaskText(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Описание новой задачи..."
                disabled={isLoading}
                style={{
                  padding: '15px 20px',
                  fontSize: '18px',
                  border: '2px solid #C18F64',
                  borderRadius: '15px',
                  flex: 1,
                  fontFamily: 'Montserrat, sans-serif',
                  backgroundColor: '#FFF9DA'
                }}
              />
              <button
                className="main-btn"
                onClick={handleAddTaskClick}
                disabled={!newTaskText.trim() || isLoading}
                style={{
                  opacity: (!newTaskText.trim() || isLoading) ? 0.6 : 1,
                  cursor: (!newTaskText.trim() || isLoading) ? 'not-allowed' : 'pointer'
                }}
              >
                {isLoading ? 'Добавление...' : 'Добавить задачу'}
              </button>
            </div>
          </div>
        </div>

        <CalendarModal
          isOpen={isModalOpen}
          onClose={() => {
            setIsModalOpen(false);
            setTempTask('');
          }}
          onAddEvent={handleAddCalendarEvent}
          taskText={tempTask}
          isLoading={isLoading}
        />
      </main>

      <Footer setCurrentPage={setCurrentPage} />
    </div>
  );
};


const Footer = ({ setCurrentPage }) => (
  <footer className="footer">
    <div className="container">
      <div className="footer-content">
        <div className="footer-icons-panel">
          <button className="icon-button" onClick={() => setCurrentPage('calendar')}>
            <img src={icon1} alt="Календарь" />
          </button>
          <button className="icon-button big" onClick={() => setCurrentPage('chat')}>
            <img src={icon2} alt="Чат" />
          </button>
          <button className="icon-button" onClick={() => setCurrentPage('stats')}>
            <img src={icon3} alt="Статистика" />
          </button>
        </div>
      </div>
    </div>
  </footer>
);

export default App;


