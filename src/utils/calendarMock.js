export const calendarMock = {
  // Получить все события
  getEvents: () => {
    try {
      const events = localStorage.getItem('googleCalendarEvents');
      return events ? JSON.parse(events) : [];
    } catch (error) {
      console.error('Error getting events:', error);
      return [];
    }
  },
  
  // Добавить новое событие
  addEvent: (event) => {
    try {
      const events = calendarMock.getEvents();
      const newEvent = {
        id: Date.now().toString(), // уникальный ID
        title: event.title,
        startTime: event.startTime,
        description: event.description || '',
        created: new Date().toISOString()
      };
      
      events.push(newEvent);
      localStorage.setItem('googleCalendarEvents', JSON.stringify(events));
      console.log('Event added to mock calendar:', newEvent);
      return newEvent;
    } catch (error) {
      console.error('Error adding event:', error);
      return null;
    }
  },
  
  // Получить события на сегодня
  getTodayEvents: () => {
    try {
      const events = calendarMock.getEvents();
      const today = new Date().toDateString();
      
      return events.filter(event => {
        const eventDate = new Date(event.startTime).toDateString();
        return eventDate === today;
      });
    } catch (error) {
      console.error('Error getting today events:', error);
      return [];
    }
  },
  
  // Получить события по дате
  getEventsByDate: (date) => {
    try {
      const events = calendarMock.getEvents();
      const targetDate = new Date(date).toDateString();
      
      return events.filter(event => {
        const eventDate = new Date(event.startTime).toDateString();
        return eventDate === targetDate;
      });
    } catch (error) {
      console.error('Error getting events by date:', error);
      return [];
    }
  },
  
  // Удалить событие
  deleteEvent: (id) => {
    try {
      const events = calendarMock.getEvents();
      const filteredEvents = events.filter(event => event.id !== id);
      localStorage.setItem('googleCalendarEvents', JSON.stringify(filteredEvents));
      console.log('Event deleted from calendar:', id);
      return true;
    } catch (error) {
      console.error('Error deleting event:', error);
      return false;
    }
  }
};
