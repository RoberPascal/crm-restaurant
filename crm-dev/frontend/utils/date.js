import { format, toZonedTime } from "date-fns-tz";
import { ru } from "date-fns/locale";

export const MSK_TZ = "Europe/Moscow";

export const getMoscowWeekdayShort = (date) => {
  const weekdays = ["ВС", "ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ"];
  const zoned = toZonedTime(date, MSK_TZ);
  return weekdays[zoned.getDay()];
};

export const getMoscowStartOfDay = (date = new Date()) => {
  const ymd = format(toZonedTime(date, MSK_TZ), "yyyy-MM-dd");
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, 3)); // 03:00 UTC = 00:00 МСК
};

export const addMoscowDays = (date, days) => {
  const ymd = format(toZonedTime(date, MSK_TZ), "yyyy-MM-dd");
  const [y, m, d] = ymd.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + days, 3));
};

export const isSameMoscowDay = (date1, date2) => {
  return (
    format(toZonedTime(date1, MSK_TZ), "yyyy-MM-dd") ===
    format(toZonedTime(date2, MSK_TZ), "yyyy-MM-dd")
  );
};

export const formatDisplayDate = (date) => {
  const today = getMoscowStartOfDay();
  const tomorrow = addMoscowDays(today, 1);
  const weekday = getMoscowWeekdayShort(date);

  if (isSameMoscowDay(date, today)) {
    return `Сегодня - ${weekday}`;
  }
  if (isSameMoscowDay(date, tomorrow)) {
    return `Завтра - ${weekday}`;
  }

  // Для остальных дат: "1 ноября - СБ"
  const formatted = format(toZonedTime(date, MSK_TZ), "d MMMM", { locale: ru });
  return `${formatted} - ${weekday}`;
};

export const formatDateForAPI = (date) => {
  return format(toZonedTime(date, MSK_TZ), "yyyy-MM-dd");
};

// Универсальный форматтер времени в HH:MM
// Поддерживает строки "HH:MM", "HH:MM:SS", ISO-строки и объекты Date
export const formatTime = (timeValue) => {
  if (!timeValue) return "—";

  // Если это строка времени в формате "HH:MM:SS" или "HH:MM"
  if (typeof timeValue === "string" && timeValue.includes(":")) {
    // Если строка содержит дату и время в формате ISO
    if (timeValue.includes("T") && timeValue.length > 10) {
      try {
        const timePart = timeValue.split("T")[1];
        return timePart.slice(0, 5);
      } catch {
        // fallthrough
      }
    }
    // Обычная строка вида HH:MM[:SS]
    return timeValue.slice(0, 5);
  }

  // Если это объект Date
  if (timeValue instanceof Date) {
    const hours = String(timeValue.getHours()).padStart(2, "0");
    const minutes = String(timeValue.getMinutes()).padStart(2, "0");
    return `${hours}:${minutes}`;
  }

  // Если пришёл объект с полями hours/minutes
  if (typeof timeValue === "object" && timeValue !== null) {
    const h = timeValue.hours ?? timeValue.HH ?? timeValue.h;
    const m = timeValue.minutes ?? timeValue.MM ?? timeValue.m;
    if (typeof h === "number" && typeof m === "number") {
      return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    }
  }

  return "—";
};
