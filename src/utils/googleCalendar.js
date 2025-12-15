class GoogleCalendarService {
  constructor() {
    this.token = null;
    this.isAuthenticated = false;
    this.SCOPES = 'https://www.googleapis.com/auth/calendar';
    
    // Ваш Client ID
    this.CLIENT_ID = '484903837238-9aeksk89vg6ktbleri8mmif1e7if1cjg.apps.googleusercontent.com';
    
    this.REDIRECT_URI = window.location.origin;
    this.authWindow = null;
  }

  // Упрощенная авторизация без проверки popup окна
  async authenticate() {
    return new Promise((resolve, reject) => {
      const state = Math.random().toString(36).substring(2);
      localStorage.setItem('google_auth_state', state);

      const authParams = new URLSearchParams({
        client_id: this.CLIENT_ID,
        redirect_uri: this.REDIRECT_URI,
        response_type: 'token',
        scope: this.SCOPES,
        state: state,
        include_granted_scopes: 'true'
      });

      const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?${authParams.toString()}`;

      // Открываем окно авторизации
      this.authWindow = window.open(
        authUrl, 
        'google_auth', 
        'width=500,height=600,left=200,top=100'
      );

      if (!this.authWindow) {
        alert('Пожалуйста, разрешите всплывающие окна для авторизации');
        reject(new Error('Popup blocked'));
        return;
      }

      // Слушаем сообщения от окна авторизации
      const messageHandler = (event) => {
        // Принимаем сообщения только от нашего origin
        if (event.origin !== window.location.origin) return;

        if (event.data.type === 'google_auth_success') {
          const token = event.data.accessToken;
          this.token = token;
          this.isAuthenticated = true;
          localStorage.setItem('google_access_token', token);
          
          window.removeEventListener('message', messageHandler);
          clearTimeout(timeoutId);
          
          if (this.authWindow) {
            this.authWindow.close();
          }
          
          resolve(true);
        }

        if (event.data.type === 'google_auth_error') {
          window.removeEventListener('message', messageHandler);
          clearTimeout(timeoutId);
          
          if (this.authWindow) {
            this.authWindow.close();
          }
          
          reject(new Error(event.data.error));
        }
      };

      window.addEventListener('message', messageHandler);

      // Таймаут
      const timeoutId = setTimeout(() => {
        window.removeEventListener('message', messageHandler);
        if (this.authWindow && !this.authWindow.closed) {
          this.authWindow.close();
        }
        reject(new Error('Auth timeout'));
      }, 60000);

      // Периодически проверяем, не закрыл ли пользователь окно
      const checkClosedInterval = setInterval(() => {
        try {
          if (this.authWindow && this.authWindow.closed) {
            clearInterval(checkClosedInterval);
            window.removeEventListener('message', messageHandler);
            clearTimeout(timeoutId);
            reject(new Error('Auth window closed by user'));
          }
        } catch (error) {
          // Игнорируем CORS ошибки при проверке closed
        }
      }, 1000);
    });
  }

  // Проверка авторизации
  async checkAuth() {
    const token = localStorage.getItem('google_access_token');
    if (token) {
      try {
        // Простая проверка токена
        const response = await fetch(
          `https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=${token}`
        );
        if (response.ok) {
          this.token = token;
          this.isAuthenticated = true;
          return true;
        } else {
          this.logout();
          return false;
        }
      } catch (error) {
        console.warn('Token validation failed, using stored token');
        this.token = token;
        this.isAuthenticated = true;
        return true;
      }
    }
    return false;
  }

  // Выход из системы
  logout() {
    this.token = null;
    this.isAuthenticated = false;
    localStorage.removeItem('google_access_token');
    
    // Деавторизация на стороне Google
    if (this.authWindow) {
      this.authWindow.close();
    }
  }

  // API запрос к Google Calendar
  async makeCalendarRequest(endpoint, options = {}) {
    if (!this.isAuthenticated) {
      throw new Error('Not authenticated');
    }

    const baseUrl = 'https://www.googleapis.com/calendar/v3';
    const url = `${baseUrl}${endpoint}`;

    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${this.token}`,
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Google API error:', response.status, errorText);
      
      if (response.status === 401) {
        this.logout();
        throw new Error('Authentication failed');
      }
      throw new Error(`Google API error: ${response.status}`);
    }

    return response.json();
  }

  // Добавление события в Google Calendar
  async addEvent(eventData) {
    console.log('📅 Adding event to Google Calendar:', eventData);
    
    const event = {
        summary: eventData.summary,
        description: eventData.description || '',
        start: {
        dateTime: eventData.startTime,
        timeZone: 'Europe/Moscow',
        },
        end: {
        dateTime: new Date(new Date(eventData.startTime).getTime() + 60 * 60 * 1000).toISOString(),
        timeZone: 'Europe/Moscow',
        },
    };

    console.log('📋 Formatted event for Google API:', event);

    try {
        const result = await this.makeCalendarRequest('/calendars/primary/events', {
        method: 'POST',
        body: JSON.stringify(event),
        });
        
        console.log('✅ Event added successfully:', result);
        return result;
    } catch (error) {
        console.error('❌ Error adding event:', error);
        throw error;
    }
    }

  // Получение событий на сегодня
  async getTodayEvents() {
    const startOfDay = new Date();
    startOfDay.setHours(0, 0, 0, 0);
    
    const endOfDay = new Date();
    endOfDay.setHours(23, 59, 59, 999);

    const timeMin = startOfDay.toISOString();
    const timeMax = endOfDay.toISOString();

    try {
      const data = await this.makeCalendarRequest(
        `/calendars/primary/events?` +
        `timeMin=${encodeURIComponent(timeMin)}&` +
        `timeMax=${encodeURIComponent(timeMax)}&` +
        `singleEvents=true&` +
        `orderBy=startTime`
      );
      
      return data.items.map(event => ({
        id: event.id,
        summary: event.summary,
        title: event.summary,
        startTime: event.start.dateTime || event.start.date,
        description: event.description,
        isGoogleEvent: true
      }));
    } catch (error) {
      console.error('Error fetching events:', error);
      return [];
    }
  }

  // Удаление события
  async deleteEvent(eventId) {
    return this.makeCalendarRequest(`/calendars/primary/events/${eventId}`, {
      method: 'DELETE',
    });
  }
}

export const googleCalendarService = new GoogleCalendarService();