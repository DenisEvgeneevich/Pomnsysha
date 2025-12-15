const SESSION_STORAGE_KEY = 'pomnyashaSessionId';

const hasWindow = () => typeof window !== 'undefined' && !!window.localStorage;

const persistSessionId = (value) => {
  if (!value || !hasWindow()) return;
  try {
    window.localStorage.setItem(SESSION_STORAGE_KEY, value);
  } catch (e) {
    console.warn('Не удалось сохранить sessionId', e);
  }
};

const readSessionId = () => {
  if (!hasWindow()) return null;
  try {
    return window.localStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
};

export const fetchWithSession = async (url, options = {}) => {
  const headers = {
    ...(options.headers || {})
  };

  const existingSession = readSessionId();
  if (existingSession) {
    headers['X-Session-Id'] = existingSession;
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include'
  });

  const nextSession = response.headers.get('X-Session-Id');
  if (nextSession && nextSession !== existingSession) {
    persistSessionId(nextSession);
  }

  return response;
};

export const clearSessionId = () => {
  if (!hasWindow()) return;
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {}
};

