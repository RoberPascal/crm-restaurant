// components/TelegramAppWrapper.jsx
"use client";

import { useEffect, useRef, useState } from "react";
import { TelegramProvider } from "@/components/TelegramProvider";

export default function TelegramAppWrapper({ children }) {
  const [loading, setLoading] = useState(true);
  const cleanupRef = useRef(null);

  useEffect(() => {
    /** Корректное скрытие всех кнопок Telegram */
    const hideButtons = (tg) => {
      try {
        tg.MainButton.hide();
        tg.BackButton.hide();
      } catch (e) {
        console.warn("Error hiding Telegram buttons:", e);
      }
    };

    const initializeTelegram = () => {
      const tg = window.Telegram?.WebApp;
      if (!tg) return false;

      console.log("Telegram WebApp detected");

      tg.ready();
      tg.expand();

      // Цвета интерфейса
      tg.setHeaderColor("#ffffff");
      tg.setBackgroundColor("#ffffff");

      // Первичное скрытие
      hideButtons(tg);

      // Повторные скрытия (боремся с glitch-и и авто-появлением кнопок)
      [100, 300, 600, 1000, 2000, 3000].forEach((delay) => {
        setTimeout(() => hideButtons(tg), delay);
      });

      // Скрываем при всех важных внутренних событиях
      const onTheme = () => hideButtons(tg);
      const onViewport = () => hideButtons(tg);
      tg.onEvent("themeChanged", onTheme);
      tg.onEvent("viewportChanged", onViewport);

      setLoading(false);
      cleanupRef.current = () => {
        tg.offEvent("themeChanged", onTheme);
        tg.offEvent("viewportChanged", onViewport);
      };
      return true;
    };

    // Повторная инициализация в случае раннего старта
    let attempts = 0;
    const interval = setInterval(() => {
      if (initializeTelegram()) {
        clearInterval(interval);
      } else {
        attempts++;
        if (attempts > 30) {
          console.log("Telegram WebApp not found — Browser mode");
          setLoading(false);
          clearInterval(interval);
        }
      }
    }, 100);

    return () => {
      clearInterval(interval);
      cleanupRef.current?.();
    };
  }, []);

  if (loading) {
    return (
      <div
        style={{
          height: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "Montserrat, sans-serif",
        }}
      >
        <div>Загрузка...</div>
      </div>
    );
  }

  return <TelegramProvider>{children}</TelegramProvider>;
}
