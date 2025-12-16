import { getTelegramHeaders } from './telegramWebApp';

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

export const fetchWithSession = async (url, options = {}) => {
  const telegramHeaders = getTelegramHeaders();
  
  const headers = {
    'Content-Type': 'application/json',
    ...telegramHeaders,
    ...options.headers
  };

  return fetch(url, {
    ...options,
    headers,
    credentials: 'include'
  });
};

export const getSessionId = () => {
  return document.cookie
    .split('; ')
    .find(row => row.startsWith('sid='))
    ?.split('=')[1];
};

