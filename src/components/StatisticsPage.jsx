import React, { useState, useEffect } from 'react';
import './StatisticsPage.css';
import { fetchWithSession, API_URL } from '../utils/session'

const StatisticsPage = ({ onBack }) => {
  const [statsData, setStatsData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    const loadStats = async () => {
      try {
        setIsLoading(true);
        setError(null);

        // ВАЖНО: никаких localhost в проде.
        // Через nginx API доступен как /api/...
        const response = await fetchWithSession('/api/stats', {
          signal: controller.signal,
        });

        if (!response.ok) {
          const text = await response.text().catch(() => '');
          throw new Error(`Не удалось загрузить статистику (${response.status}). ${text}`);
        }

        const data = await response.json();
        setStatsData(data);
      } catch (err) {
        if (err?.name === 'AbortError') return;
        console.error('Ошибка загрузки статистики:', err);
        setError(err?.message || 'Ошибка загрузки статистики');
      } finally {
        setIsLoading(false);
      }
    };

    loadStats();

    return () => controller.abort();
  }, []);

  if (isLoading) {
    return (
      <div className="statistics-page">
        <header className="stats-header">
          <button className="back-button" onClick={onBack}>
            ← Вернуться назад
          </button>
        </header>
        <div className="stats-content" style={{ textAlign: 'center', padding: '50px' }}>
          <p>Загрузка статистики...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="statistics-page">
        <header className="stats-header">
          <button className="back-button" onClick={onBack}>
            ← Вернуться назад
          </button>
        </header>
        <div className="stats-content" style={{ textAlign: 'center', padding: '50px' }}>
          <p>Ошибка загрузки: {error}</p>
        </div>
      </div>
    );
  }

  const { weeklyStats = [], pieData = [], mostBusyDay, totalEvents = 0 } = statsData || {};

  const renderPieChart = () => {
    if (!pieData || pieData.length === 0) {
      return (
        <g>
          <circle cx="100" cy="100" r="80" fill="#E0E0E0" />
          <text x="100" y="100" textAnchor="middle" dominantBaseline="middle" fill="#666" fontSize="14">
            Нет данных
          </text>
        </g>
      );
    }

    let currentAngle = 0;

    return pieData.map((category) => {
      const angle = (category.value / 100) * 360;
      const startAngle = currentAngle;
      const endAngle = currentAngle + angle;
      currentAngle = endAngle;

      const startX = 100 + 80 * Math.cos((startAngle - 90) * (Math.PI / 180));
      const startY = 100 + 80 * Math.sin((startAngle - 90) * (Math.PI / 180));
      const endX = 100 + 80 * Math.cos((endAngle - 90) * (Math.PI / 180));
      const endY = 100 + 80 * Math.sin((endAngle - 90) * (Math.PI / 180));

      const largeArcFlag = angle > 180 ? 1 : 0;

      const pathData = [
        `M 100 100`,
        `L ${startX} ${startY}`,
        `A 80 80 0 ${largeArcFlag} 1 ${endX} ${endY}`,
        'Z'
      ].join(' ');

      return (
        <g key={category.name}>
          <path d={pathData} fill={category.color} stroke="#FFF9DA" strokeWidth="2" />

          {category.value > 5 && (
            <text
              x={100 + 40 * Math.cos((startAngle + angle / 2 - 90) * (Math.PI / 180))}
              y={100 + 40 * Math.sin((startAngle + angle / 2 - 90) * (Math.PI / 180))}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="white"
              fontSize="12"
              fontWeight="bold"
              className="pie-percentage"
            >
              {category.value}%
            </text>
          )}
        </g>
      );
    });
  };

  const maxTasks = weeklyStats.length > 0 ? Math.max(...weeklyStats.map(d => d.tasks)) : 0;

  return (
    <div className="statistics-page">
      <header className="stats-header">
        <button className="back-button" onClick={onBack}>
          ← Вернуться назад
        </button>
      </header>

      <div className="stats-content">
        <div className="stats-section">
          <h2>Статистика задач ({totalEvents} всего)</h2>

          <div className="pie-chart-container">
            <svg width="200" height="200" viewBox="0 0 200 200" className="pie-chart">
              {renderPieChart()}
              <circle cx="100" cy="100" r="30" fill="#FFF9DA" />
            </svg>

            <div className="pie-legend">
              {pieData && pieData.length > 0 ? (
                pieData.map((category) => (
                  <div key={category.name} className="legend-item">
                    <div className="legend-color" style={{ backgroundColor: category.color }}></div>
                    <span className="legend-name">{category.name}</span>
                    <span className="legend-value">{category.value}%</span>
                  </div>
                ))
              ) : (
                <div className="no-data-message">
                  <p>Нет данных для отображения</p>
                  <p>Добавьте задачи, чтобы увидеть статистику</p>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="stats-section">
          <h2>Загруженность по дням недели</h2>

          <div className="days-stats">
            {weeklyStats && weeklyStats.length > 0 ? (
              weeklyStats.map(day => (
                <div key={day.day} className={`day-item ${day.isMostBusy ? 'most-busy' : ''}`}>
                  <span className="day-name">{day.day}</span>

                  <div className="day-tasks">
                    <span className="tasks-count">{day.tasks} задач</span>
                    <div
                      className="tasks-bar"
                      style={{
                        width: maxTasks > 0 ? `${(day.tasks / maxTasks) * 100}%` : '0%'
                      }}
                    ></div>
                  </div>
                </div>
              ))
            ) : (
              <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                Нет данных о задачах
              </div>
            )}
          </div>

          {mostBusyDay && mostBusyDay.tasks > 0 && (
            <div className="most-busy-day">
              <div className="most-busy-badge">Самый загруженный день</div>
              <div className="most-busy-content">
                <span className="most-busy-name">{mostBusyDay.day}</span>
                <span className="most-busy-tasks">{mostBusyDay.tasks} задач</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StatisticsPage;
