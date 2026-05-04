"use client";

import { useState, useEffect, useCallback } from "react";
import { addDays, format } from "date-fns";
import { ru } from "date-fns/locale";
import { toZonedTime } from "date-fns-tz"; // ✅ современный импорт

export const useRestaurantStatus = (scheduleItem = []) => {
  const [statusInfo, setStatusInfo] = useState({
    status: "Уточняется",
    time: "",
    isOpen: false,
  });

  // Получаем московское время независимо от часового пояса пользователя
  const getMoscowTime = useCallback(() => {
    const now = new Date();
    return toZonedTime(now, "Europe/Moscow"); // ✅ правильная замена utcToZonedTime
  }, []);

  const dayNames = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"];

  const getCurrentDayName = (date) => {
    const dayMap = {
      0: "ВС",
      1: "ПН",
      2: "ВТ",
      3: "СР",
      4: "ЧТ",
      5: "ПТ",
      6: "СБ",
    };
    return dayMap[date.getDay()];
  };

  const schedule = useCallback(() => {
    return dayNames.map((day) => {
      const item = scheduleItem.find((s) => s.dayName === day);
      return {
        day,
        hours: item
          ? `${item.open.slice(0, 5)} - ${item.close.slice(0, 5)}`
          : "Выходной",
      };
    });
  }, [scheduleItem]);

  const findNextOpenDay = useCallback(
    (currentTime, scheduleItem) => {
      const currentDayName = getCurrentDayName(currentTime);
      const currentDayIndex = dayNames.indexOf(currentDayName);

      for (let i = 1; i <= 7; i++) {
        const nextDayIndex = (currentDayIndex + i) % 7;
        const nextDayName = dayNames[nextDayIndex];
        const nextDaySchedule = scheduleItem.find(
          (s) => s.dayName === nextDayName
        );

        if (nextDaySchedule?.open && nextDaySchedule?.close) {
          const [nextOpenH, nextOpenM] = nextDaySchedule.open
            .slice(0, 5)
            .split(":")
            .map(Number);

          const nextDay = addDays(currentTime, i);
          const nextOpenTime = new Date(nextDay);
          nextOpenTime.setHours(nextOpenH, nextOpenM, 0, 0);

          let displayText;
          if (i === 1) {
            displayText = "откроется завтра в ";
          } else {
            const dateFormat = format(nextOpenTime, "d MMMM", { locale: ru });
            displayText = `откроется ${dateFormat} в `;
          }

          const timeFormatted = format(nextOpenTime, "HH:mm");

          return {
            status: "Закрыто",
            time: `${displayText}${timeFormatted}`,
            isOpen: false,
          };
        }
      }

      return { status: "Закрыто", time: "", isOpen: false };
    },
    [scheduleItem]
  );

  const calculateStatus = useCallback(() => {
    try {
      const moscowTime = getMoscowTime();
      const currentDayName = getCurrentDayName(moscowTime);

      const currentScheduleItem = scheduleItem.find(
        (s) => s.dayName === currentDayName
      );

      if (!currentScheduleItem?.open || !currentScheduleItem?.close) {
        return findNextOpenDay(moscowTime, scheduleItem);
      }

      const [openH, openM] = currentScheduleItem.open
        .slice(0, 5)
        .split(":")
        .map(Number);
      const [closeH, closeM] = currentScheduleItem.close
        .slice(0, 5)
        .split(":")
        .map(Number);

      const today = new Date(moscowTime);
      today.setHours(0, 0, 0, 0);

      const openTime = new Date(today);
      openTime.setHours(openH, openM, 0, 0);

      const closeTime = new Date(today);
      closeTime.setHours(closeH, closeM, 0, 0);

      if (closeTime < openTime) closeTime.setDate(closeTime.getDate() + 1);

      const isOpen = moscowTime >= openTime && moscowTime <= closeTime;

      if (isOpen) {
        const closeFormatted = format(closeTime, "HH:mm");
        return {
          status: "Открыто",
          time: `до ${closeFormatted}`,
          isOpen: true,
        };
      } else if (moscowTime < openTime) {
        const openFormatted = format(openTime, "HH:mm");
        return {
          status: "Закрыто",
          time: `откроется сегодня в ${openFormatted}`,
          isOpen: false,
        };
      } else {
        return findNextOpenDay(moscowTime, scheduleItem);
      }
    } catch (error) {
      console.error("Ошибка расчета статуса:", error);
      return { status: "Уточняется", time: "", isOpen: false };
    }
  }, [scheduleItem, findNextOpenDay, getMoscowTime]);

  useEffect(() => {
    const updateStatus = () => {
      const newStatus = calculateStatus();
      setStatusInfo(newStatus);
    };

    updateStatus();
    const interval = setInterval(updateStatus, 60000);
    return () => clearInterval(interval);
  }, [calculateStatus]);

  return { statusInfo, schedule: schedule() };
};
