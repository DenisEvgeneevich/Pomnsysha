const getTelegramUser = () => {
  if (typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp) {
    const webApp = window.Telegram.WebApp;
    webApp.ready();
    return {
      id: webApp.initDataUnsafe?.user?.id || null,
      username: webApp.initDataUnsafe?.user?.username || null,
      first_name: webApp.initDataUnsafe?.user?.first_name || null,
      last_name: webApp.initDataUnsafe?.user?.last_name || null,
      isTelegram: true
    };
  }
  return { isTelegram: false };
};

const getTelegramHeaders = () => {
  const user = getTelegramUser();
  const headers = {};
  
  if (user.isTelegram && user.id) {
    headers['X-Telegram-User-ID'] = user.id.toString();
  }
  
  return headers;
};

const isTelegramWebApp = () => {
  return typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp;
};

export { getTelegramUser, getTelegramHeaders, isTelegramWebApp };

