import React, { useState, useEffect } from 'react';
import './CalendarModal.css';

const getInitialDate = () => {
  const d = new Date();
  return d.toISOString().split('T')[0];
};

const getInitialTime = () => {
  const d = new Date();
  d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5);

  // Получаем локальное время вместо UTC
  const hours = String(d.getHours()).padStart(2, '0');
  const minutes = String(d.getMinutes()).padStart(2, '0');

  return `${hours}:${minutes}`;
};

const CalendarModal = ({ isOpen, onClose, onAddEvent, taskText, isLoading }) => {
  const [date, setDate] = useState(getInitialDate());
  const [time, setTime] = useState(getInitialTime());
  const [description, setDescription] = useState('');

  useEffect(() => {
    if (isOpen) {
      setDate(getInitialDate());
      setTime(getInitialTime());
      setDescription('');
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!date || !time) {
      alert('Укажи дату и время');
      return;
    }

    const baseDate = new Date(`${date}T${time}:00`);
    if (Number.isNaN(baseDate.getTime())) {
      alert('Некорректная дата или время');
      return;
    }

    const offsetMinutes = baseDate.getTimezoneOffset() * -1;
    const sign = offsetMinutes >= 0 ? '+' : '-';
    const absOffset = Math.abs(offsetMinutes);
    const offsetHours = String(Math.floor(absOffset / 60)).padStart(2, '0');
    const offsetMins = String(absOffset % 60).padStart(2, '0');
    const localizedIso = `${date}T${time}:00${sign}${offsetHours}:${offsetMins}`;

    await onAddEvent({
      startTime: localizedIso,
      description
    });
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h2>Добавить событие</h2>

        <div className="task-preview">
          <strong>Задача:</strong> {taskText}
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Дата</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label>Время</label>
            <input
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              required
            />
          </div>

          <div className="form-group">
            <label>Описание</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Комментарий"
            />
          </div>

          <div className="modal-actions">
            <button type="button" onClick={onClose}>Отмена</button>

            <button type="submit" disabled={isLoading}>
              {isLoading ? '...' : 'Добавить'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CalendarModal;
