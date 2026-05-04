// components/TelegramProvider.jsx
"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

const TelegramContext = createContext({});

export function TelegramProvider({ children }) {
  const [webApp, setWebApp] = useState(null);
  const [user, setUser] = useState(null);

  useEffect(() => {
    const app = window.Telegram?.WebApp;

    if (app) {
      // Режим Telegram - используем реальные данные
      setWebApp(app);
      setUser(app.initDataUnsafe?.user || null);
    } else {
      // Режим браузера - создаем mock пользователя
      const mockUser = {
        id: 999999999,
        first_name: "Гость",
        last_name: "",
        username: "guest",
      };
      setUser(mockUser);
      console.log("Running in browser mode with guest user");
    }
  }, []);

  const value = useMemo(
    () => ({
      webApp,
      user,
      isTelegram: !!webApp,
    }),
    [webApp, user],
  );

  return (
    <TelegramContext.Provider value={value}>
      {children}
    </TelegramContext.Provider>
  );
}

export const useTelegram = () => useContext(TelegramContext);
