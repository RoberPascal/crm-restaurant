"use client";

import { useState, useEffect, useCallback } from "react";
import { toZonedTime } from "date-fns-tz";

export const useMoscowTime = () => {
  const getMoscowTime = useCallback(() => {
    return toZonedTime(new Date(), "Europe/Moscow");
  }, []);

  const [moscowTime, setMoscowTime] = useState(getMoscowTime);

  useEffect(() => {
    // Correct any SSR/CSR drift on mount
    setMoscowTime(getMoscowTime());

    const interval = setInterval(() => {
      setMoscowTime(getMoscowTime());
    }, 60000); // Обновляем каждую минуту

    return () => clearInterval(interval);
  }, [getMoscowTime]);

  return moscowTime;
};
