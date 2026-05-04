// components/BookingModal/BookingModal.jsx
"use client";
import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  format,
  addDays,
  isSameDay,
  startOfDay,
  startOfMonth,
  getDay,
  getDaysInMonth,
} from "date-fns";
import { toZonedTime } from "date-fns-tz/toZonedTime";
import { ru } from "date-fns/locale";
import styles from "./BookingModal.module.scss";
import { api } from "@/utils/api";

// ОПТИМИЗАЦИЯ: Логирование только в dev-режиме
const IS_DEV = process.env.NODE_ENV === "development";
const debugLog = IS_DEV ? console.log.bind(console) : () => {};
const debugWarn = IS_DEV ? console.warn.bind(console) : () => {};
const debugError = IS_DEV ? console.error.bind(console) : () => {};

/* ---------- Иконки ---------- */
const CalendarIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <rect
      x="3"
      y="6"
      width="18"
      height="15"
      rx="2"
      stroke="currentColor"
      strokeWidth="1.5"
    />
    <path
      d="M3 10H21"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path
      d="M8 3V6"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path
      d="M16 3V6"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);
const UserIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.5" />
    <path
      d="M20 20C20 16.6863 16.4183 14 12 14C7.58172 14 4 16.6863 4 20"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);
const CloseIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
    <path
      d="M18 6L6 18M6 6l12 12"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
const CheckmarkIcon = () => (
  <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
    <circle cx="32" cy="32" r="32" fill="#4CAF50" />
    <path
      d="M44 22L28 38L20 30"
      stroke="white"
      strokeWidth="4"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
const WarningIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
    <path
      d="M12 9V14M12 17V17.01M3 12C3 13.1819 3.23279 14.3522 3.68508 15.4442C4.13738 16.5361 4.80031 17.5282 5.63604 18.364C6.47177 19.1997 7.46392 19.8626 8.55585 20.3149C9.64778 20.7672 10.8181 21 12 21C13.1819 21 14.3522 20.7672 15.4442 20.3149C16.5361 19.8626 17.5282 19.1997 18.364 18.364C19.1997 17.5282 19.8626 16.5361 20.3149 15.4442C20.7672 14.3522 21 13.1819 21 12C21 10.8181 20.7672 9.64778 20.3149 8.55585C19.8626 7.46392 19.1997 6.47177 18.364 5.63604C17.5282 4.80031 16.5361 4.13738 15.4442 3.68508C14.3522 3.23279 13.1819 3 12 3C10.8181 3 9.64778 3.23279 8.55585 3.68508C7.46392 4.13738 6.47177 4.80031 5.63604 5.63604C4.80031 6.47177 4.13738 7.46392 3.68508 8.55585C3.23279 9.64778 3 10.8181 3 12Z"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
    />
  </svg>
);

const ACTIVE_BOOKING_STATUSES = [
  "pending",
  "pending_review",
  "confirmed",
  "assigned",
  "arrived",
];

/* ---------- Утилиты ---------- */
const normalizePhone = (phone) => {
  let cleaned = phone.replace(/\D/g, "");
  if (cleaned.startsWith("8")) {
    cleaned = "7" + cleaned.slice(1);
  } else if (!cleaned.startsWith("7")) {
    cleaned = "7" + cleaned;
  }
  if (cleaned.length > 11) {
    cleaned = cleaned.slice(0, 11);
  }
  return `+${cleaned}`;
};

/* ---------- Получение last_booking_time ---------- */
const fetchLastBookingTime = async (slug) => {
  try {
    const response = await api.get(
      `/api/v1/public/restaurant/${slug}/last-booking-time`,
    );

    // Простая логика извлечения last_booking_time
    let value = null;

    if (response?.data?.last_booking_time) {
      value = String(response.data.last_booking_time).trim();
    } else if (response?.last_booking_time) {
      value = String(response.last_booking_time).trim();
    }

    debugLog(`Last booking time for ${slug}:`, value);
    return value;
  } catch (error) {
    debugWarn("last_booking_time не загружен, считаем null", error);
    return null;
  }
};

const formatPhoneDisplay = (phone) => {
  const cleaned = phone.replace(/\D/g, "");
  if (cleaned.length === 0) return "";
  let formatted = "+7";
  if (cleaned.length > 1) formatted += ` (${cleaned.slice(1, 4)}`;
  if (cleaned.length > 4) formatted += `) ${cleaned.slice(4, 7)}`;
  if (cleaned.length > 7) formatted += `-${cleaned.slice(7, 9)}`;
  if (cleaned.length > 9) formatted += `-${cleaned.slice(9, 11)}`;
  return formatted;
};

const isValidPhone = (phone) => {
  const cleaned = phone.replace(/\D/g, "");
  if (cleaned.length !== 11) return false;

  // Проверка первой цифры (7 или 8 для РФ)
  if (!["7", "8"].includes(cleaned[0])) return false;

  // Проверка второй цифры (код региона не может начинаться с 0, 1, 2)
  // В РФ коды обычно начинаются с 3, 4, 8, 9
  const areaFirstDigit = cleaned[1];
  if (["0", "1", "2"].includes(areaFirstDigit)) return false;

  return true;
};

const buildFullName = (firstName, lastName) => {
  const parts = [];
  // user-related name utilities removed
  return [firstName?.trim(), lastName?.trim()].filter(Boolean).join(" ");
};

const splitFullName = (fullName) => {
  if (!fullName) return ["", ""];
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return ["", ""];
  const firstName = parts.shift() || "";
  const lastName = parts.length > 0 ? parts.join(" ") : "";
  return [firstName, lastName];
};

// ДОБАВЛЕНО: makeSlotsKey ВНЕ компонента
const makeSlotsKey = (slots) => {
  if (!slots || !Array.isArray(slots)) return "empty";
  return slots
    .map(
      (s) =>
        `${s.time}:${s.available ? "avail" : "unavail"}:${
          s.available_table_count || 0
        }`,
    )
    .join("|");
};

// Функция для правильного спряжения слова "стол"
const getTableWord = (count) => {
  const mod10 = count % 10;
  const mod100 = count % 100;

  if (mod100 >= 11 && mod100 <= 19) {
    return "столов";
  }
  if (mod10 === 1) {
    return "стол";
  }
  if (mod10 >= 2 && mod10 <= 4) {
    return "стола";
  }
  return "столов";
};

const formatTime = (timeValue) => {
  if (!timeValue) return "—";

  const normalizeString = (value) => {
    let t = value;
    if (t.includes("T")) t = t.split("T")[1];
    if (t.includes(" ")) t = t.split(" ")[1];
    return t;
  };

  if (typeof timeValue === "string" && timeValue.includes(":")) {
    const clean = normalizeString(timeValue);
    const parts = clean.split(":");
    if (parts.length >= 2) {
      const hours = parts[0].padStart(2, "0");
      const minutes = parts[1].padStart(2, "0");
      return `${hours}:${minutes}`;
    }
    return clean.slice(0, 5);
  }

  if (timeValue instanceof Date) {
    return timeValue.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return "—";
};

/* ---------- Хук текущего времени в МСК ---------- */
const useMoscowTime = () => {
  const [moscowTime, setMoscowTime] = useState(() =>
    toZonedTime(new Date(), "Europe/Moscow"),
  );
  useEffect(() => {
    const update = () =>
      setMoscowTime(toZonedTime(new Date(), "Europe/Moscow"));
    update();
    const id = setInterval(update, 60_000);
    return () => clearInterval(id);
  }, []);
  return moscowTime;
};

/* ---------- Утилита: начало дня в МСК ---------- */
const getMoscowStartOfDay = (date = new Date()) => {
  const zoned = toZonedTime(date, "Europe/Moscow");
  return startOfDay(zoned);
};

/* ---------- Форматирование даты для кнопки ---------- */
const formatDisplayDate = (date) => {
  const today = getMoscowStartOfDay();
  const tomorrow = addDays(today, 1);
  if (isSameDay(date, today)) return "Сегодня";
  if (isSameDay(date, tomorrow)) return "Завтра";
  return format(date, "d MMM", { locale: ru }).replace(".", "");
};

/* ---------- Улучшенный WebSocket хук ---------- */
const useWebSocket = (
  isOpen,
  restaurantSlug,
  selectedDateStr,
  guests,
  onMessage,
) => {
  const wsRef = useRef(null);
  const [isWsConnected, setIsWsConnected] = useState(false);
  const reconnectTimeoutRef = useRef(null);
  const connectionTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);
  const currentUrlRef = useRef("");
  const onMessageRef = useRef(onMessage);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;

  const createWebSocketUrl = useCallback((slug, date, guestsCount) => {
    const apiUrl =
      process.env.NEXT_PUBLIC_CRM_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "";
    if (!apiUrl) {
      console.warn("No API URL configured for WebSocket connection");
      return null;
    }
    let wsBase;
    if (apiUrl.startsWith("https://")) {
      wsBase = apiUrl.replace("https://", "wss://");
    } else if (apiUrl.startsWith("http://")) {
      wsBase = apiUrl.replace("http://", "ws://");
    } else {
      wsBase = apiUrl;
    }
    return `${wsBase}/ws/public/slots/${slug}/${date}?guests=${guestsCount}`;
  }, []);

  const connect = useCallback(
    (slug, date, guestsCount) => {
      if (!slug || !date) return;

      const wsUrl = createWebSocketUrl(slug, date, guestsCount);
      if (!wsUrl) return;

      // Если уже подключены к этому URL - не переподключаемся
      if (
        wsUrl === currentUrlRef.current &&
        wsRef.current?.readyState === WebSocket.OPEN
      ) {
        debugLog("✅ Already connected to", wsUrl);
        return;
      }

      // Очищаем предыдущее соединение
      if (wsRef.current) {
        debugLog("🔄 Closing previous WebSocket connection");
        try {
          wsRef.current.close(1000, "Changing connection");
        } catch (e) {
          debugWarn("Error closing previous WS:", e);
        }
        wsRef.current = null;
      }

      // Очищаем таймауты
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current);
        connectionTimeoutRef.current = null;
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }

      currentUrlRef.current = wsUrl;
      setIsWsConnected(false);

      debugLog("🔌 Connecting to WebSocket:", wsUrl);

      try {
        const socket = new WebSocket(wsUrl);

        // Таймаут подключения (10 секунд)
        connectionTimeoutRef.current = setTimeout(() => {
          if (socket.readyState !== WebSocket.OPEN) {
            debugError("❌ WebSocket connection timeout");
            socket.close();
            setIsWsConnected(false);

            // Пробуем переподключиться
            if (isOpen && reconnectAttemptsRef.current < maxReconnectAttempts) {
              reconnectAttemptsRef.current++;
              const delay = Math.min(
                1000 * Math.pow(2, reconnectAttemptsRef.current),
                10000,
              );
              debugLog(
                `⏳ Reconnect attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts} in ${delay}ms`,
              );
              reconnectTimeoutRef.current = setTimeout(
                () => connect(slug, date, guestsCount),
                delay,
              );
            } else {
              debugError("❌ Max reconnection attempts reached");
              if (onMessageRef.current) {
                onMessageRef.current({
                  type: "connection_status",
                  connected: false,
                  error: "Не удалось подключиться к серверу",
                });
              }
            }
          }
        }, 10000);

        socket.onopen = () => {
          debugLog("✅ WebSocket connected");
          if (connectionTimeoutRef.current) {
            clearTimeout(connectionTimeoutRef.current);
            connectionTimeoutRef.current = null;
          }
          reconnectAttemptsRef.current = 0;
          setIsWsConnected(true);

          // Ping каждые 25 секунд для keepalive
          pingIntervalRef.current = setInterval(() => {
            if (socket.readyState === WebSocket.OPEN) {
              try {
                socket.send(JSON.stringify({ action: "ping" }));
              } catch (e) {
                debugWarn("Ping failed:", e);
              }
            }
          }, 25000);

          if (onMessageRef.current) {
            onMessageRef.current({
              type: "connection_status",
              connected: true,
            });
          }
        };

        socket.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            if (msg.type !== "pong") {
              // Игнорируем pong
              if (onMessageRef.current) {
                onMessageRef.current(msg);
              }
            }
          } catch (err) {
            debugError("WebSocket parse error:", err);
          }
        };

        socket.onerror = (error) => {
          debugError("❌ WebSocket error:", error);
          setIsWsConnected(false);
        };

        socket.onclose = (e) => {
          debugLog("🔌 WebSocket closed:", e.code, e.reason);
          setIsWsConnected(false);

          if (connectionTimeoutRef.current) {
            clearTimeout(connectionTimeoutRef.current);
            connectionTimeoutRef.current = null;
          }
          if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
          }

          // Переподключаемся только если модал открыт и это не нормальное закрытие
          if (e.code !== 1000 && isOpen && currentUrlRef.current === wsUrl) {
            if (reconnectAttemptsRef.current < maxReconnectAttempts) {
              reconnectAttemptsRef.current++;
              const delay = Math.min(
                1000 * Math.pow(2, reconnectAttemptsRef.current),
                10000,
              );
              debugLog(
                `⏳ Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`,
              );
              reconnectTimeoutRef.current = setTimeout(
                () => connect(slug, date, guestsCount),
                delay,
              );
            } else {
              debugError("❌ Max reconnection attempts reached");
            }
          }
        };

        wsRef.current = socket;
      } catch (error) {
        debugError("❌ WebSocket creation error:", error);
        setIsWsConnected(false);

        if (isOpen && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          const delay = Math.min(
            1000 * Math.pow(2, reconnectAttemptsRef.current),
            10000,
          );
          reconnectTimeoutRef.current = setTimeout(
            () => connect(slug, date, guestsCount),
            delay,
          );
        }
      }
    },
    [isOpen, createWebSocketUrl, onMessageRef, maxReconnectAttempts],
  );

  useEffect(() => {
    if (!isOpen || !restaurantSlug || !selectedDateStr) {
      debugLog("🔌 Closing WebSocket: modal closed or no params");
      if (wsRef.current) {
        try {
          wsRef.current.close(1000, "Modal closed");
        } catch (e) {
          debugWarn("Error closing WS:", e);
        }
        wsRef.current = null;
      }
      setIsWsConnected(false);
      currentUrlRef.current = "";
      reconnectAttemptsRef.current = 0;

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current);
        connectionTimeoutRef.current = null;
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }
      return;
    }

    debugLog("🔌 WebSocket effect triggered:", {
      restaurantSlug,
      selectedDateStr,
    });
    connect(restaurantSlug, selectedDateStr, guests);

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current);
        connectionTimeoutRef.current = null;
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }
    };
  }, [isOpen, restaurantSlug, selectedDateStr, guests, connect]);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify(message));
        return true;
      } catch (error) {
        debugError("Error sending WebSocket message:", error);
        return false;
      }
    } else {
      debugWarn("WebSocket not connected");
      return false;
    }
  }, []);

  const closeConnection = useCallback((reason = "Manual close") => {
    debugLog("🔌 Manually closing WebSocket:", reason);
    if (wsRef.current) {
      try {
        wsRef.current.close(1000, reason);
      } catch (e) {
        debugWarn("Error closing WS:", e);
      }
      wsRef.current = null;
    }
    setIsWsConnected(false);
    currentUrlRef.current = "";
    reconnectAttemptsRef.current = 0;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (connectionTimeoutRef.current) {
      clearTimeout(connectionTimeoutRef.current);
      connectionTimeoutRef.current = null;
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  return { isWsConnected, sendMessage, closeConnection };
};

/* ---------- Компоненты шагов ---------- */
const StepGuests = React.memo(
  ({
    guests,
    onGuestsChange,
    bookingError,
    onNext,
    restaurantData,
    // repeat booking blocking removed
    bookingsLoading,
    bookingsError,
  }) => {
    const safeRestaurantData = restaurantData || {};
    // Removed max_guests_for_online logic: always allow online booking

    return (
      <motion.div className={styles.stepContent}>
        <h3>Количество гостей</h3>
        <div className={styles.guestsSection}>
          <div className={styles.guestsControl}>
            <motion.button
              className={styles.counterBtn}
              onClick={() => onGuestsChange(-1)}
              whileTap={{ scale: 0.95 }}
              disabled={guests <= 2}
            >
              −
            </motion.button>
            <div className={styles.guestsDisplay}>
              <UserIcon />
              <span>
                {guests}{" "}
                {guests === 1 ? "гость" : guests <= 4 ? "гостя" : "гостей"}
              </span>
            </div>
            <motion.button
              className={styles.counterBtn}
              onClick={() => onGuestsChange(1)}
              whileTap={{ scale: 0.95 }}
              disabled={guests >= 15}
            >
              +
            </motion.button>
          </div>
        </div>
        {bookingsLoading && (
          <p
            style={{
              fontSize: "13px",
              color: "#6b7280",
              margin: "0 0 12px",
            }}
          >
            Проверяем ваши активные брони...
          </p>
        )}
        {bookingError && (
          <div className={styles.bookingError}>
            <WarningIcon />
            <span>{bookingError}</span>
          </div>
        )}
        <div className={styles.navigation}>
          <motion.button
            className={styles.nextButton}
            onClick={() => {
              onNext();
            }}
            disabled={bookingsLoading}
            whileTap={{ scale: 0.98 }}
          >
            {bookingsLoading ? "Подождите..." : "Далее"}
          </motion.button>
        </div>
      </motion.div>
    );
  },
);

const StepDateTime = React.memo(
  ({
    selectedDate,
    selectedTimeSlot,
    showDatePicker,
    availableSlots,
    loadingSlots,
    bookingError,
    isWsConnected,
    submitLoading,
    onDateChange,
    onShowDatePickerChange,
    onTimeSlotSelect,
    onBack,
    onNext,
    selectedStartTime,
    selectedEndTime,
    availableEndTimes,
    loadingEndTimes,
    freeTablesAvailable,
    suggestedEndTime,
    onEndTimeSelect,
    restaurant,
    lastBookingTime,
    restaurantSlug,
    // repeat booking blocking removed
    bookingsLoading,
  }) => {
    const moscowNow = useMoscowTime();
    const currentMinutesToday =
      moscowNow.getHours() * 60 + moscowNow.getMinutes();
    const isToday = isSameDay(selectedDate, getMoscowStartOfDay());

    // Мемоизируем парсинг времени
    const timeParseCache = useRef(new Map());
    const timeToMinutes = useCallback((time) => {
      if (timeParseCache.current.has(time)) {
        return timeParseCache.current.get(time);
      }
      const [h, m] = time.split(":").map(Number);
      const result = h * 60 + m;
      timeParseCache.current.set(time, result);
      if (timeParseCache.current.size > 100) {
        const firstKey = timeParseCache.current.keys().next().value;
        timeParseCache.current.delete(firstKey);
      }
      return result;
    }, []);

    const displayedSlots = useMemo(() => {
      if (!Array.isArray(availableSlots)) return [];

      const rawLastBookingTime = lastBookingTime;
      const hasLastBookingTime =
        rawLastBookingTime && String(rawLastBookingTime).trim() !== "";

      const nowMinutes = currentMinutesToday;
      // FIX: Removed shadowed isToday — use the one from outer scope

      // ОПТИМИЗАЦИЯ: Объединяем все фильтры в один проход
      const limitMinutes = hasLastBookingTime
        ? timeToMinutes(String(rawLastBookingTime).trim())
        : null;

      // Прекэшируем закрытие и длительность
      const getClosingTime = () => {
        if (!restaurant?.working_hours) return "02:00";
        try {
          const workingHours =
            typeof restaurant.working_hours === "string"
              ? JSON.parse(restaurant.working_hours)
              : restaurant.working_hours;
          const dayOfWeek = selectedDate.getDay();
          const todaySchedule = workingHours.find((wh) => wh.day === dayOfWeek);
          return todaySchedule?.close || "02:00";
        } catch (e) {
          return "02:00";
        }
      };

      const closingTime = getClosingTime();
      const closingMinutes = timeToMinutes(closingTime);
      const MIN_BOOKING_DURATION = 120;

      // FIX: Merged two-pass filtering into a single pass
      return availableSlots.filter((slot) => {
        // Быстрая проверка: должен быть доступен и иметь столы
        if (!slot.available || slot.available_table_count === 0) return false;

        const slotMinutes = timeToMinutes(slot.time);

        // Проверка last_booking_time
        if (limitMinutes !== null) {
          // Убираем ВСЕ, что >= last_booking_time
          if (slotMinutes >= limitMinutes) return false;

          // Убираем ночные слоты (00:00–05:59), если last_booking_time задан
          if (slotMinutes < 360 && limitMinutes >= 720) {
            return false;
          }
        }

        // Убираем прошедшие слоты только сегодня
        if (isToday && slotMinutes < nowMinutes) return false;

        // Cross-midnight validation using linear (unwrapped) comparison
        const endMinutes = slotMinutes + MIN_BOOKING_DURATION;
        let closeNorm = closingMinutes;
        if (closeNorm <= slotMinutes) closeNorm += 24 * 60;
        if (endMinutes > closeNorm) return false;

        return true;
      });
    }, [
      availableSlots,
      lastBookingTime,
      restaurant?.working_hours,
      selectedDate,
      currentMinutesToday,
      isToday,
      timeToMinutes,
    ]);

    return (
      <motion.div className={styles.stepContent}>
        <h3>Выберите дату и время</h3>

        <div className={styles.dateSection}>
          <motion.button
            className={styles.dateDisplay}
            onClick={() => onShowDatePickerChange(!showDatePicker)}
            whileTap={{ scale: 0.98 }}
          >
            <CalendarIcon />
            <span>{formatDisplayDate(selectedDate)}</span>
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              className={`${styles.chevron} ${
                showDatePicker ? styles.chevronOpen : ""
              }`}
            >
              <path d="M6 9L12 15L18 9" stroke="currentColor" strokeWidth="2" />
            </svg>
          </motion.button>
          <AnimatePresence>
            {showDatePicker && (
              <motion.div
                className={styles.calendarContainer}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
              >
                <Calendar
                  selectedDate={selectedDate}
                  onDateChange={onDateChange}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <div className={styles.timeSection}>
          <h4>Доступное время:</h4>
          <div
            className={styles.timeGrid}
            style={{ position: "relative", minHeight: 180 }}
          >
            {loadingSlots && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background: "rgba(255,255,255,0.6)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  pointerEvents: "none",
                  zIndex: 1,
                }}
              >
                <div className={styles.spinner} />
              </div>
            )}
            {!bookingError && displayedSlots.length > 0 ? (
              displayedSlots.map((slot) => {
                const isSelected = selectedTimeSlot?.time === slot.time;
                return (
                  <motion.button
                    key={slot.time}
                    className={`${styles.timeSlot} ${
                      isSelected ? styles.selected : ""
                    }`}
                    onClick={() => {
                      const newSlot = { time: slot.time };
                      onTimeSlotSelect(newSlot);
                    }}
                    whileTap={{ scale: 0.98 }}
                  >
                    {slot.time}
                    {typeof slot.available_table_count === "number" && (
                      <span className={styles.tableCount}>
                        {slot.available_table_count}{" "}
                        {getTableWord(slot.available_table_count)}
                      </span>
                    )}
                  </motion.button>
                );
              })
            ) : (
              <div
                className={styles.noSlots}
                style={{ gridColumn: "1 / -1", width: "100%" }}
              >
                <p>{bookingError || "На эту дату мест нет"}</p>
                <motion.button
                  className={styles.changeDateBtn}
                  onClick={() => onShowDatePickerChange(true)}
                  whileTap={{ scale: 0.98 }}
                >
                  Изменить дату
                </motion.button>
              </div>
            )}
          </div>
        </div>

        {selectedStartTime &&
          !loadingEndTimes &&
          availableEndTimes.length > 0 && (
            <div className={styles.timeSection}>
              <h4>Выберите время окончания:</h4>
              <div className={styles.timeGrid} style={{ position: "relative" }}>
                {availableEndTimes.map((endTime) => {
                  const isSelected = selectedEndTime === endTime;
                  const [startH, startM] = selectedStartTime
                    .split(":")
                    .map(Number);
                  const [endH, endM] = endTime.split(":").map(Number);
                  const startMinutes = startH * 60 + startM;
                  const endMinutes = endH * 60 + endM;
                  let durationMinutes = endMinutes - startMinutes;
                  if (durationMinutes < 0) durationMinutes += 24 * 60;
                  const hours = Math.floor(durationMinutes / 60);
                  const mins = durationMinutes % 60;
                  const durationText =
                    hours > 0 ? `${hours}ч ${mins}м` : `${mins}м`;
                  return (
                    <motion.button
                      key={endTime}
                      className={`${styles.timeSlot} ${
                        isSelected ? styles.selected : ""
                      }`}
                      onClick={() => onEndTimeSelect(endTime)}
                      whileTap={{ scale: 0.98 }}
                      title={`Бронь с ${selectedStartTime} до ${endTime}`}
                    >
                      <div>{endTime}</div>
                      <div
                        style={{
                          fontSize: "12px",
                          opacity: 0.7,
                          marginTop: "2px",
                        }}
                      >
                        {durationText}
                      </div>
                    </motion.button>
                  );
                })}
              </div>
            </div>
          )}

        {selectedStartTime && loadingEndTimes && (
          <div className={styles.timeSection}>
            <h4>Загружаем доступное время окончания...</h4>
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                padding: "20px",
              }}
            >
              <div className={styles.spinner} />
            </div>
          </div>
        )}

        {selectedStartTime &&
          !loadingEndTimes &&
          availableEndTimes.length === 0 &&
          !freeTablesAvailable && (
            <div
              style={{
                padding: "16px",
                marginTop: "16px",
                backgroundColor: "#fef3c7",
                border: "1px solid #fde68a",
                borderRadius: "8px",
                color: "#92400e",
                fontSize: "14px",
                textAlign: "center",
              }}
            >
              ⚠️ <strong>Столы на это время ограничены</strong>
              <br />
              Бронь будет создана до закрытия. При необходимости измените время.
            </div>
          )}

        {bookingsLoading && (
          <p
            style={{
              fontSize: "13px",
              color: "#6b7280",
              margin: "0 0 12px",
            }}
          >
            Проверяем ваши активные брони...
          </p>
        )}
        {bookingError && !loadingSlots && availableSlots.length > 0 && (
          <div className={styles.bookingError}>
            <WarningIcon />
            <span>{bookingError}</span>
          </div>
        )}

        <div className={styles.navigation}>
          <motion.button
            className={styles.backButton}
            onClick={onBack}
            whileTap={{ scale: 0.98 }}
          >
            Назад
          </motion.button>
          <motion.button
            className={styles.nextButton}
            onClick={onNext}
            disabled={
              !selectedTimeSlot ||
              (availableEndTimes.length > 0 && !selectedEndTime) ||
              submitLoading ||
              !isWsConnected ||
              loadingEndTimes ||
              false
            }
            whileTap={{ scale: 0.98 }}
          >
            {submitLoading ? (
              <>
                <div className={styles.spinner} />
                Блокируем...
              </>
            ) : !isWsConnected ? (
              <>
                <div className={styles.spinner} />
                Подключаемся...
              </>
            ) : !selectedTimeSlot ? (
              "Выберите время"
            ) : loadingEndTimes ? (
              "Загружаем..."
            ) : availableEndTimes.length > 0 && !selectedEndTime ? (
              "Выберите конец"
            ) : (
              "Далее"
            )}
          </motion.button>
        </div>
      </motion.div>
    );
  },
);

const StepContacts = React.memo(
  ({
    userName,
    userPhone,
    wishes,
    guests,
    bookingError,
    submitLoading,
    profileLoading,
    profileError,
    // repeat booking blocking removed
    bookingsLoading,
    onNameChange,
    onPhoneChange,
    onWishesChange,
    onBack,
    onBooking,
    privacyAccepted, // ← ДОБАВЛЕНО
    onPrivacyAcceptedChange, // ← ДОБАВЛЕНО
  }) => {
    return (
      <motion.div className={styles.stepContent}>
        <h3>Контактная информация</h3>
        {profileLoading && (
          <p
            style={{
              fontSize: "13px",
              color: "#6b7280",
              margin: "0 0 12px",
            }}
          >
            Загружаем сохраненные данные профиля...
          </p>
        )}
        {profileError && !profileLoading && (
          <p
            style={{
              fontSize: "13px",
              color: "#b45309",
              margin: "0 0 12px",
            }}
          >
            {profileError}
          </p>
        )}
        {bookingsLoading && (
          <p
            style={{
              fontSize: "13px",
              color: "#6b7280",
              margin: "0 0 12px",
            }}
          >
            Проверяем ваши активные брони...
          </p>
        )}

        <div className={styles.contactForm}>
          <div className={styles.inputGroup}>
            <label>Ваше имя</label>
            <input
              type="text"
              value={userName}
              onChange={onNameChange}
              placeholder="Иван Иванов"
              required
            />
          </div>
          <div className={styles.inputGroup}>
            <label>Телефон</label>
            <input
              type="tel"
              value={userPhone}
              onChange={onPhoneChange}
              placeholder="+7 (999) 999-99-99"
              required
            />
          </div>
          <div className={styles.inputGroup}>
            <label>Пожелания</label>
            <textarea
              value={wishes}
              onChange={onWishesChange}
              placeholder="Особые пожелания к столику, аллергии..."
              rows={3}
            />
          </div>
        </div>
        {bookingError && (
          <div className={styles.bookingError}>
            <WarningIcon />
            <span>{bookingError}</span>
            {
              <motion.button
                className={styles.retryBtn}
                onClick={onBooking}
                whileTap={{ scale: 0.98 }}
              >
                Попробовать снова
              </motion.button>
            }
          </div>
        )}
        <div className={styles.navigation}>
          <motion.button
            className={styles.backButton}
            onClick={onBack}
            whileTap={{ scale: 0.98 }}
          >
            Назад
          </motion.button>
          <motion.button
            className={styles.bookButton}
            onClick={onBooking}
            disabled={
              !userName.trim() || !userPhone || submitLoading || bookingsLoading
            }
            whileTap={{ scale: 0.98 }}
          >
            {submitLoading ? (
              <>
                <div className={styles.spinner} />
                Отправляем...
              </>
            ) : (
              "Забронировать"
            )}
          </motion.button>
        </div>
      </motion.div>
    );
  },
);

const StepSuccess = React.memo(
  ({
    restaurant,
    selectedTimeSlot,
    guests,
    userPhone,
    selectedDate,
    selectedStartTime,
    selectedEndTime,
    confirmedStartTime,
    confirmedEndTime,
    onClose,
  }) => {
    const displayStartTime =
      confirmedStartTime || selectedStartTime || selectedTimeSlot?.time;
    const displayEndTime = confirmedEndTime || selectedEndTime;

    return (
      <motion.div className={styles.stepContent}>
        <div className={styles.thanksIcon}>
          <CheckmarkIcon />
        </div>
        <h3>Бронь подтверждена!</h3>
        <div className={styles.bookingSummary}>
          <div className={styles.summaryItem}>
            <span>Бар:</span>
            <span>{restaurant.name}</span>
          </div>
          <div className={styles.summaryItem}>
            <span>Дата:</span>
            <span>{formatDisplayDate(selectedDate)}</span>
          </div>
          <div className={styles.summaryItem}>
            <span>Время:</span>
            <span>
              {displayEndTime
                ? `${formatTime(displayStartTime)} - ${formatTime(
                    displayEndTime,
                  )}`
                : formatTime(displayStartTime)}
            </span>
          </div>
          <div className={styles.summaryItem}>
            <span>Гостей:</span>
            <span>{guests} чел</span>
          </div>
        </div>
        <motion.button
          className={styles.thanksButton}
          onClick={onClose}
          whileTap={{ scale: 0.98 }}
        >
          Понятно
        </motion.button>
      </motion.div>
    );
  },
);

/* ---------- Календарь компонент ---------- */
const Calendar = React.memo(({ selectedDate, onDateChange }) => {
  const [currentMonth, setCurrentMonth] = useState(selectedDate);
  // FIX: Memoize maxDate to avoid recalculating addDays on every render
  const maxDate = useMemo(() => addDays(getMoscowStartOfDay(), 60), []);
  const getFirstDayOfMonth = (date) => {
    const firstDay = startOfMonth(date);
    const day = getDay(firstDay);
    return day === 0 ? 6 : day - 1;
  };
  const calendarDays = useMemo(() => {
    const days = [];
    const daysInMonth = getDaysInMonth(currentMonth);
    const firstDay = getFirstDayOfMonth(currentMonth);
    for (let i = 0; i < firstDay; i++) {
      days.push(<div key={`empty-${i}`} className={styles.calendarEmpty} />);
    }
    for (let day = 1; day <= daysInMonth; day++) {
      const mskDate = toZonedTime(
        new Date(
          currentMonth.getFullYear(),
          currentMonth.getMonth(),
          day,
          12,
          0,
          0,
        ),
        "Europe/Moscow",
      );
      const isSelected = isSameDay(mskDate, selectedDate);
      const isToday = isSameDay(mskDate, getMoscowStartOfDay());
      const isPast = mskDate < getMoscowStartOfDay();
      const isFuture = mskDate > maxDate;
      days.push(
        <button
          key={day}
          className={`${styles.calendarDay} ${
            isSelected ? styles.selected : ""
          } ${isToday ? styles.today : ""} ${
            isPast || isFuture ? styles.past : ""
          }`}
          onClick={() => {
            if (!isPast && !isFuture) {
              onDateChange(mskDate);
            }
          }}
          disabled={isPast || isFuture}
        >
          {day}
        </button>,
      );
    }
    return days;
  }, [currentMonth, selectedDate, maxDate, onDateChange]);
  const goToPreviousMonth = () => {
    const prevMonth = toZonedTime(
      new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 15),
      "Europe/Moscow",
    );
    setCurrentMonth(prevMonth);
  };
  const goToNextMonth = () => {
    const nextMonth = toZonedTime(
      new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 15),
      "Europe/Moscow",
    );
    setCurrentMonth(nextMonth);
  };
  return (
    <div className={styles.calendar}>
      <div className={styles.calendarHeader}>
        <button
          onClick={goToPreviousMonth}
          className={styles.calendarNavButton}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M15 18L9 12L15 6" stroke="currentColor" strokeWidth="2" />
          </svg>
        </button>
        <span className={styles.calendarMonth}>
          {format(currentMonth, "LLLL yyyy", { locale: ru }).replace(
            /^\w/,
            (c) => c.toUpperCase(),
          )}
        </span>
        <button onClick={goToNextMonth} className={styles.calendarNavButton}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M9 18L15 12L9 6" stroke="currentColor" strokeWidth="2" />
          </svg>
        </button>
      </div>
      <div className={styles.calendarWeekdays}>
        {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((d) => (
          <div key={d} className={styles.calendarWeekday}>
            {d}
          </div>
        ))}
      </div>
      <div className={styles.calendarGrid}>{calendarDays}</div>
    </div>
  );
});

/* ---------- Основной компонент ---------- */
export default function AdminBookingModal({
  isOpen,
  onClose,
  restaurant,
  preselectedTime,
  preselectedDate,
  restaurantSlug,
}) {
  // FIX: Removed unused useMoscowTime() — was triggering re-renders every 60s
  // StepDateTime has its own useMoscowTime() call
  const modalRef = useRef(null);

  const [selectedDate, setSelectedDate] = useState(() => {
    if (preselectedDate) return getMoscowStartOfDay(new Date(preselectedDate));
    return getMoscowStartOfDay();
  });
  const [guests, setGuests] = useState(2);
  const [selectedTimeSlot, setSelectedTimeSlot] = useState(null);
  // user-related state removed
  const [wishes, setWishes] = useState("");
  const [userName, setUserName] = useState("");
  const [userPhone, setUserPhone] = useState("");
  const [activeStep, setActiveStep] = useState(1);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [availableSlots, setAvailableSlots] = useState([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [bookingError, setBookingError] = useState(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [lockedSlot, setLockedSlot] = useState(null);
  const [lockValue, setLockValue] = useState(null);

  // Refs для доступа к состоянию внутри cleanup и WS callbacks
  const lockedSlotRef = useRef(null);
  const lockValueRef = useRef(null);
  const activeStepRef = useRef(activeStep);

  useEffect(() => {
    lockedSlotRef.current = lockedSlot;
  }, [lockedSlot]);

  useEffect(() => {
    lockValueRef.current = lockValue;
  }, [lockValue]);

  useEffect(() => {
    activeStepRef.current = activeStep;
  }, [activeStep]);

  const [selectedStartTime, setSelectedStartTime] = useState(null);
  const [selectedEndTime, setSelectedEndTime] = useState(null);
  // Сохраняем время, подтверждённое в бронировании, чтобы не терять его при обновлениях слотов
  const [confirmedStartTime, setConfirmedStartTime] = useState(null);
  const [confirmedEndTime, setConfirmedEndTime] = useState(null);
  const [availableEndTimes, setAvailableEndTimes] = useState([]);
  const [loadingEndTimes, setLoadingEndTimes] = useState(false);
  const [freeTablesAvailable, setFreeTablesAvailable] = useState(false);
  const [suggestedEndTime, setSuggestedEndTime] = useState(null);
  const [lastBookingTime, setLastBookingTime] = useState(null);

  const lockPromiseRef = useRef(null);
  const pendingLockTimeRef = useRef(null);
  const wsUpdateTimerRef = useRef(null);
  const lastSlotsKeyRef = useRef("");
  const lastDateRef = useRef("");
  const nameTouchedRef = useRef(false);
  const phoneTouchedRef = useRef(false);
  const guestsRef = useRef(guests);
  // FIX: Guard against double-click on "Next" button
  const lockingRef = useRef(false);
  // FIX: Track setTimeouts so they can be cleared on unmount/reset
  const bookingConfirmTimerRef = useRef(null);
  const redirect409TimerRef = useRef(null);

  // Обновляем ref при изменении guests
  useEffect(() => {
    guestsRef.current = guests;
  }, [guests]);

  // privacy consent removed

  // repeat booking blocking removed: no fetch/refresh bookings

  useEffect(() => {
    if (!restaurantSlug || !isOpen) return;

    fetchLastBookingTime(restaurantSlug).then((time) => {
      debugLog("Глобально загружен last_booking_time:", time);
      setLastBookingTime(time);
    });
  }, [restaurantSlug, isOpen]);

  // ПЕРЕМЕЩЕНО: groupSlotsByTime ВЫШЕ loadAvailableSlots
  const groupSlotsByTime = useCallback((slots) => {
    const timeMap = new Map();
    for (const slot of slots || []) {
      if (slot.available && !timeMap.has(slot.time)) {
        timeMap.set(slot.time, {
          time: slot.time,
          available: true,
          available_table_count: slot.available_table_count,
          total_table_count: slot.total_table_count,
          status: slot.status,
          table_ids: slot.table_ids,
          meta: slot.meta,
        });
      }
    }
    return Array.from(timeMap.values());
  }, []);

  // ПЕРЕМЕЩЕНО: loadAvailableSlots ВЫШЕ useEffect
  const loadAvailableSlots = useCallback(
    async (date) => {
      if (!restaurantSlug || !date) return;
      const dateStr = format(date, "yyyy-MM-dd");

      setLoadingSlots(true);
      setBookingError(null);
      try {
        // ДОБАВЬ TIMESTAMP ДЛЯ ОБХОДА КЭШИРОВАНИЯ
        const timestamp = Date.now();
        const data = await api.get(
          `/api/v1/public/slots/availability?restaurant_slug=${restaurantSlug}&booking_date=${dateStr}&total_guests=${guests}&t=${timestamp}`,
        );

        const groupedSlots = groupSlotsByTime(data.slots || data);
        setAvailableSlots(groupedSlots);
      } catch (err) {
        debugError("Ошибка загрузки слотов:", err);
        setBookingError(err.message || "Не удалось загрузить время");
        setAvailableSlots([]);
        setSelectedTimeSlot(null);
      } finally {
        setLoadingSlots(false);
      }
    },
    [restaurantSlug, guests, groupSlotsByTime],
  );

  // Теперь useEffect может использовать loadAvailableSlots
  useEffect(() => {
    if (isOpen && selectedDate && activeStep >= 2) {
      debugLog("🔄 Loading slots:", {
        guests,
        date: format(selectedDate, "yyyy-MM-dd"),
        activeStep,
      });
      loadAvailableSlots(selectedDate);
    }
  }, [guests, isOpen, selectedDate, activeStep, loadAvailableSlots]);

  // Auto-refresh removed: WebSocket slots_updated messages already handle real-time updates.
  // HTTP polling was redundant and stressed the API under 10+ concurrent users.

  const resetModal = useCallback(() => {
    setActiveStep(1);
    setShowDatePicker(false);
    setSelectedTimeSlot(null);
    // user-related state reset removed
    setUserName("");
    setUserPhone("");
    setWishes("");
    setGuests(2);
    setBookingError(null);
    setAvailableSlots([]);
    setLockedSlot(null);
    setLockValue(null);
    setSubmitLoading(false);
    setLoadingSlots(false);
    setSelectedStartTime(null);
    setSelectedEndTime(null);
    setConfirmedStartTime(null);
    setConfirmedEndTime(null);
    setAvailableEndTimes([]);
    setLoadingEndTimes(false);
    setFreeTablesAvailable(false);
    setSuggestedEndTime(null);
    nameTouchedRef.current = false;
    phoneTouchedRef.current = false;
    lastDateRef.current = "";
    lastSlotsKeyRef.current = "";
    lockingRef.current = false;
    // FIX: Clear tracked timeouts on reset
    if (bookingConfirmTimerRef.current) {
      clearTimeout(bookingConfirmTimerRef.current);
      bookingConfirmTimerRef.current = null;
    }
    if (redirect409TimerRef.current) {
      clearTimeout(redirect409TimerRef.current);
      redirect409TimerRef.current = null;
    }
  }, []);

  const selectedDateStr = useMemo(
    () => format(selectedDate, "yyyy-MM-dd"),
    [selectedDate],
  );

  // repeat booking blocking removed: no block messages or flags

  const handleWebSocketMessage = useCallback(
    (msg) => {
      const processSlotsUpdate = (slotsPayload) => {
        const grouped = groupSlotsByTime(slotsPayload);

        // ОПТИМИЗАЦИЯ: сравниваем хеш слотов перед обновлением
        // Это предотвращает ненужные перерисовки когда ничего не изменилось
        setAvailableSlots((prevSlots) => {
          // Быстрое сравнение: проверяем длину и ключевые поля
          if (prevSlots.length === grouped.length) {
            let isSame = true;
            for (let i = 0; i < prevSlots.length; i++) {
              if (
                prevSlots[i].time !== grouped[i].time ||
                prevSlots[i].available !== grouped[i].available ||
                prevSlots[i].available_table_count !==
                  grouped[i].available_table_count
              ) {
                isSame = false;
                break;
              }
            }
            // Если ничего не изменилось, не обновляем состояние
            if (isSame) {
              return prevSlots;
            }
          }
          return grouped;
        });

        // Проверяем, доступен ли выбранный слот после обновления
        if (selectedTimeSlot) {
          const stillAvailable = grouped.some(
            (s) => s.time === selectedTimeSlot.time && s.available,
          );
          if (!stillAvailable) {
            setSelectedTimeSlot(null);
            setSelectedStartTime(null);
            setSelectedEndTime(null);
            setAvailableEndTimes([]);
            setBookingError("Выбранное время больше не доступно");
          }
        }
      };

      switch (msg.type) {
        case "connection_status":
          if (msg.connected) {
            debugLog("✅ WebSocket connected state ready");
            setBookingError(null);
            // ПРИМЕЧАНИЕ: Мы не отправляем request_initial_slots здесь,
            // так как сервер уже получил количество гостей через query параметры
            // и автоматически прислал initial_slots.
          } else if (msg.error) {
            debugError("❌ WebSocket connection error:", msg.error);
            setBookingError(
              "Не удалось подключиться к серверу. Перезагрузите страницу.",
            );
          }
          break;
        case "initial_slots":
        case "slots_updated":
          processSlotsUpdate(msg.slots);
          break;
        case "slot_locked":
          const msgTime = msg.time?.includes(":")
            ? msg.time.split(":").slice(0, 2).join(":")
            : msg.time;
          const pendingTime = pendingLockTimeRef.current
            ?.split(":")
            .slice(0, 2)
            .join(":");

          debugLog("slot_locked received:", {
            msgTime,
            pendingTime,
            hasPromise: !!lockPromiseRef.current,
          });

          if (pendingTime === msgTime && lockPromiseRef.current) {
            const newLockValue = msg.lock_value;
            if (newLockValue) {
              debugLog("✅ Lock confirmed:", {
                time: msgTime,
                lock_value: newLockValue.substring(0, 8) + "...",
              });
              lockPromiseRef.current.resolve({ lock_value: newLockValue });
              // FIX: Null the ref after resolve to prevent stale references
              lockPromiseRef.current = null;
              pendingLockTimeRef.current = null;
              setLockValue(newLockValue);
              setLockedSlot(msgTime);
              setBookingError(null);
            } else {
              debugError("❌ No lock_value in slot_locked response");
              lockPromiseRef.current.reject(
                new Error("No lock_value in response"),
              );
              lockPromiseRef.current = null;
              pendingLockTimeRef.current = null;
            }
          } else {
            debugWarn("⚠️ Received slot_locked but not waiting for it:", {
              msgTime,
              pendingTime,
            });
          }
          break;
        case "booking_confirmed":
          if (lockedSlotRef.current === msg.time) {
            setLockedSlot(null);
            setLockValue(null);
            if (activeStepRef.current === 3) {
              // FIX: Use tracked timeout; bookingError was incorrectly used for success
              setBookingError(null);
              bookingConfirmTimerRef.current = setTimeout(() => {
                setActiveStep(4);
                bookingConfirmTimerRef.current = null;
              }, 500);
            }
          }
          break;
        case "slot_unlocked":
          debugLog("slot_unlocked received:", {
            time: msg.time,
            currentLocked: lockedSlotRef.current,
          });
          if (lockedSlotRef.current === msg.time) {
            debugLog("✅ Slot unlocked successfully:", msg.time);
            setLockedSlot(null);
            setLockValue(null);
          }
          break;
        case "error":
          const errorMsg = msg.message || "";
          debugError("❌ WebSocket error:", errorMsg);

          if (
            errorMsg.includes("already locked") ||
            errorMsg === "Slot already locked"
          ) {
            setBookingError("Слот уже занят другим пользователем");
            if (lockPromiseRef.current) {
              lockPromiseRef.current.reject(new Error("Locked"));
              lockPromiseRef.current = null;
            }
            pendingLockTimeRef.current = null;
            // Обновляем список доступных слотов
            if (sendMessage) {
              sendMessage({
                action: "request_initial_slots",
                total_guests: guestsRef.current,
              });
            }
          } else if (
            errorMsg.includes("not available") ||
            errorMsg === "Slot not available" ||
            errorMsg.includes(
              "missing 1 required positional argument: 'total_guests'",
            )
          ) {
            setBookingError(
              "Выбранное время недоступно. Пожалуйста, выберите другое.",
            );
            if (lockPromiseRef.current) {
              lockPromiseRef.current.reject(new Error("Not available"));
              lockPromiseRef.current = null;
            }
            pendingLockTimeRef.current = null;
            setSelectedTimeSlot(null);
            setSelectedStartTime(null);
            setSelectedEndTime(null);
            setAvailableEndTimes([]);
            if (sendMessage) {
              sendMessage({
                action: "request_initial_slots",
                total_guests: guestsRef.current,
              });
            }
          } else if (errorMsg) {
            setBookingError(errorMsg);
            if (lockPromiseRef.current) {
              lockPromiseRef.current.reject(new Error(errorMsg));
              lockPromiseRef.current = null;
            }
            pendingLockTimeRef.current = null;
          }
          break;
        default:
          break;
      }
    },
    [selectedTimeSlot],
  );

  const { isWsConnected, sendMessage, closeConnection } = useWebSocket(
    isOpen,
    restaurantSlug,
    selectedDateStr,
    guests,
    handleWebSocketMessage,
  );

  const loadAvailableEndTimes = useCallback(
    async (startTime) => {
      if (!restaurantSlug || !selectedDate || !startTime) return;
      setLoadingEndTimes(true);
      setSelectedEndTime(null);
      try {
        const dateStr = format(selectedDate, "yyyy-MM-dd");
        const currentGuests = guestsRef.current;
        const response = await api.get(
          `/api/v1/public/slots/end-times?restaurant_slug=${restaurantSlug}&booking_date=${dateStr}&start_time=${startTime}&total_guests=${currentGuests}`,
        );

        // ДЛЯ ОТЛАДКИ
        debugLog("Available end times response:", response);

        setFreeTablesAvailable(Boolean(response.free_tables_available));
        setSuggestedEndTime(response.suggested_end_time || null);
        if (
          response.available_end_times &&
          Array.isArray(response.available_end_times)
        ) {
          setAvailableEndTimes(response.available_end_times);
        } else {
          setAvailableEndTimes([]);
        }
      } catch (err) {
        debugError("Ошибка загрузки конечных времен:", err);
        setAvailableEndTimes([]);
        setFreeTablesAvailable(false);
        setSuggestedEndTime(null);
        setBookingError(
          "Не удалось загрузить доступное время окончания бронирования",
        );
      } finally {
        setLoadingEndTimes(false);
      }
    },
    [restaurantSlug, selectedDate],
  );

  // REMOVED: Redundant slot loading effect (was firing without activeStep >= 2 guard).
  // The primary effect above (with activeStep >= 2) already handles slot loading.

  const unlockCurrentSlot = useCallback(async () => {
    debugLog("🔓 unlockCurrentSlot called:", {
      lockedSlot,
      lockValue: lockValue ? lockValue.substring(0, 8) + "..." : null,
      isWsConnected,
    });

    // Отменяем pending блокировку
    if (lockPromiseRef.current) {
      debugLog("⚠️ Cancelling pending lock promise");
      lockPromiseRef.current.reject(new Error("Cancelled by navigation"));
      lockPromiseRef.current = null;
    }
    pendingLockTimeRef.current = null;

    // Отправляем unlock только если есть активная блокировка
    if (lockedSlot && lockValue) {
      if (!isWsConnected || !sendMessage) {
        debugWarn("⚠️ Cannot unlock: WebSocket not connected");
        // Всё равно сбрасываем локальное состояние
        setLockedSlot(null);
        setLockValue(null);
        return;
      }

      try {
        const unlockMessage = {
          action: "unlock_slot",
          time: lockedSlot,
          lock_value: lockValue,
          total_guests: guestsRef.current,
        };

        debugLog("📤 Sending unlock message:", {
          time: lockedSlot,
          lock_value: lockValue.substring(0, 8) + "...",
        });
        const sent = sendMessage(unlockMessage);

        if (sent) {
          debugLog("✅ Unlock message sent successfully");
          // Даём небольшую задержку для обработки на сервере
          await new Promise((resolve) => setTimeout(resolve, 100));
        } else {
          debugWarn("⚠️ Failed to send unlock message (WS not ready)");
        }
      } catch (error) {
        debugError("❌ Error sending unlock message:", error);
      }
    } else {
      debugLog("ℹ️ No slot to unlock");
    }

    // ВСЕГДА СБРАСЫВАЕМ СОСТОЯНИЕ
    setLockedSlot(null);
    setLockValue(null);
  }, [lockedSlot, lockValue, isWsConnected, sendMessage]);

  const handleDateChange = useCallback(
    async (newDate) => {
      await unlockCurrentSlot();
      setSelectedDate(newDate);
      setSelectedTimeSlot(null);
      setSelectedStartTime(null);
      setSelectedEndTime(null);
      setAvailableEndTimes([]);
      setFreeTablesAvailable(false);
      setSuggestedEndTime(null);
      setBookingError(null);
      // loadAvailableSlots will be triggered by the useEffect watching selectedDate
    },
    [unlockCurrentSlot],
  );

  const handleNextFromGuests = () => {
    // repeat booking blocking removed
    if (guests < 2 || guests > 15) {
      setBookingError("Гостей: 2–15");
      return;
    }
    setActiveStep(2);
  };

  const handleNextFromTime = async () => {
    // FIX: Guard against double-click rapid invocation
    if (lockingRef.current) return;
    // repeat booking blocking removed
    if (!selectedTimeSlot) {
      setBookingError("Выберите время");
      return;
    }
    if (availableEndTimes.length > 0 && !selectedEndTime) {
      setBookingError("Выберите время окончания бронирования");
      return;
    }
    // Админ может создать бронь без выбора окончания — бронь будет до закрытия
    if (!isWsConnected) {
      setBookingError(
        "Подключение к серверу не установлено. Подождите или перезагрузите страницу.",
      );
      return;
    }

    lockingRef.current = true;
    setSubmitLoading(true);
    setBookingError(null);
    const timeSlot = selectedTimeSlot.time.split(":").slice(0, 2).join(":");

    debugLog("🔒 Starting lock process for slot:", timeSlot);

    // Разблокируем предыдущий слот, если был заблокирован другой
    if (lockedSlot && lockedSlot !== timeSlot) {
      debugLog("🔄 Unlocking previous slot before locking new one");
      await unlockCurrentSlot();
      // Даём серверу время обработать разблокировку
      await new Promise((resolve) => setTimeout(resolve, 200));
    }

    try {
      const lockPromise = new Promise((resolve, reject) => {
        lockPromiseRef.current = { resolve, reject };
      });
      pendingLockTimeRef.current = timeSlot;

      const lockMessage = {
        action: "lock_slot",
        time: timeSlot,
        end_time: selectedEndTime,
        total_guests: guestsRef.current,
      };

      debugLog("📤 Sending lock message:", lockMessage);

      const sent = sendMessage(lockMessage);
      if (!sent) {
        debugError("❌ Failed to send lock message - WS not connected");
        throw new Error("Failed to send lock request");
      }

      debugLog("⏳ Waiting for lock confirmation...");
      const lockResult = await Promise.race([
        lockPromise,
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error("Timeout")), 10000),
        ),
      ]);

      debugLog("✅ Lock result received:", {
        time: timeSlot,
        lock_value: lockResult?.lock_value?.substring(0, 8) + "...",
      });

      if (!lockResult?.lock_value) {
        debugError("❌ No lock_value in response");
        throw new Error("No lock_value received");
      }

      // Сохраняем lockValue ДО перехода к следующему шагу
      setLockValue(lockResult.lock_value);
      setLockedSlot(timeSlot);
      setBookingError(null);

      debugLog("✅ Slot locked successfully, moving to step 3");
      // ПЕРЕХОДИМ К СЛЕДУЮЩЕМУ ШАГУ ТОЛЬКО ПОСЛЕ УСПЕШНОЙ БЛОКИРОВКИ
      setActiveStep(3);
    } catch (err) {
      debugError("❌ Lock error:", err.message);

      const errorMessage =
        err.message === "Timeout"
          ? "Превышено время ожидания. Попробуйте еще раз."
          : err.message === "Locked"
            ? "Слот уже занят другим пользователем."
            : err.message === "Not available"
              ? "Выбранное время недоступно."
              : err.message === "Failed to send lock request"
                ? "WebSocket не подключен. Перезагрузите страницу."
                : err.message === "Cancelled by user"
                  ? "Отменено пользователем"
                  : "Не удалось заблокировать слот. Попробуйте другое время.";

      setBookingError(errorMessage);

      // Очищаем состояние при ошибке
      await unlockCurrentSlot();

      // ОБНОВЛЯЕМ СЛОТЫ ПРИ ОШИБКЕ (кроме отмены пользователем)
      if (err.message !== "Cancelled by user") {
        loadAvailableSlots(selectedDate);
      }
    } finally {
      lockPromiseRef.current = null;
      pendingLockTimeRef.current = null;
      setSubmitLoading(false);
      lockingRef.current = false;
    }
  };

  const handleBooking = async () => {
    // Admin booking with customer details
    if (!lockedSlot || !lockValue) {
      setBookingError("Слот потерян. Вернитесь назад.");
      setActiveStep(2);
      return;
    }
    if (guests < 2 || guests > 15) {
      setBookingError("Неверное количество гостей (2-15)");
      return;
    }
    if (!isValidPhone(userPhone) || !userName.trim()) {
      setBookingError("Укажите имя и корректный телефон");
      return;
    }

    const normalizedPhone = normalizePhone(userPhone);

    // Capture the booking times upfront to avoid losing them if state updates during async operations
    const bookedStartTime = selectedStartTime || selectedTimeSlot?.time;
    const bookedEndTime = selectedEndTime;

    const bookingData = {
      restaurant_slug: restaurantSlug,
      date: selectedDateStr,
      time: bookedStartTime,
      end_time: bookedEndTime,
      adults: guests,
      children: 0,
      name: userName.trim(),
      phone: normalizedPhone,
      wishes: wishes.trim() || null,
      lock_value: lockValue,
      table_id: null,
      idempotency_key: crypto.randomUUID(),
    };

    debugLog("Admin booking payload:", bookingData);

    setSubmitLoading(true);
    setBookingError(null);
    try {
      await api.post("/api/v1/admin/bookings/", bookingData);
      // Сохраняем подтвержденное время, чтобы не потерять его при обновлениях слотов
      setConfirmedStartTime(bookedStartTime);
      setConfirmedEndTime(bookedEndTime);
      setActiveStep(4);
      setLockedSlot(null);
      setLockValue(null);
    } catch (err) {
      debugError("Ошибка бронирования:", err);
      let errorMessage = err.message || "Ошибка при создании бронирования";
      if (
        err.status === 409 ||
        /already occupied|slot may be occupied/i.test(err.message)
      ) {
        errorMessage =
          "Это время уже занято. Пожалуйста, выберите другое время.";
        // FIX: Use tracked timeout
        redirect409TimerRef.current = setTimeout(() => {
          setActiveStep(2);
          setBookingError(null);
          redirect409TimerRef.current = null;
        }, 3000);
      }
      setBookingError(errorMessage);
      await unlockCurrentSlot();
    } finally {
      setSubmitLoading(false);
    }
  };

  // user input handlers removed
  const handleNameChange = (e) => {
    nameTouchedRef.current = true;
    setUserName(e.target.value.replace(/[^a-zA-Z\u0400-\u04FF\s]/g, ""));
  };
  const handlePhoneChange = (e) => {
    phoneTouchedRef.current = true;
    const input = e.target.value;
    // Форматируем телефон по мере ввода
    const formatted = formatPhoneDisplay(input);
    setUserPhone(formatted);
  };
  const handleWishesChange = (e) => setWishes(e.target.value.slice(0, 128));
  const handleGuestsChange = async (delta) => {
    const newGuests = Math.max(2, Math.min(15, guests + delta));

    // СБРАСЫВАЕМ ВСЕ СОСТОЯНИЯ
    await unlockCurrentSlot();
    setGuests(newGuests);
    setSelectedTimeSlot(null);
    setSelectedStartTime(null);
    setSelectedEndTime(null);
    setAvailableEndTimes([]);
    setFreeTablesAvailable(false);
    setSuggestedEndTime(null);
    setBookingError(null);
    // FIX: Removed explicit setTimeout + loadAvailableSlots call here.
    // The useEffect [guests, isOpen, selectedDate, activeStep, loadAvailableSlots]
    // will re-fire automatically when `guests` changes via setGuests above.
    // This prevents double/triple slot fetching.
  };

  useEffect(() => {
    return () => {
      // Cleanup при размонтировании компонента
      if (wsUpdateTimerRef.current) {
        clearTimeout(wsUpdateTimerRef.current);
      }
      // FIX: Clear all tracked timeouts
      if (bookingConfirmTimerRef.current) {
        clearTimeout(bookingConfirmTimerRef.current);
      }
      if (redirect409TimerRef.current) {
        clearTimeout(redirect409TimerRef.current);
      }
      if (lockPromiseRef.current) {
        lockPromiseRef.current.reject(new Error("Компонент размонтирован"));
        lockPromiseRef.current = null;
      }
      pendingLockTimeRef.current = null;

      // Пытаемся разблокировать слот перед закрытием
      if (lockedSlotRef.current && lockValueRef.current) {
        try {
          if (sendMessage) {
            sendMessage({
              action: "unlock_slot",
              time: lockedSlotRef.current,
              lock_value: lockValueRef.current,
              total_guests: guestsRef.current,
            });
            debugLog("Auto-unlock on unmount sent");
          }
        } catch (err) {
          debugError("Failed to auto-unlock on unmount:", err);
        }
      }

      closeConnection();
    };
  }, [closeConnection, sendMessage]);

  const handleClose = async () => {
    await unlockCurrentSlot();
    closeConnection();
    resetModal();
    onClose();
  };

  const stepGuestsProps = {
    guests,
    bookingError,
    onGuestsChange: handleGuestsChange,
    onNext: handleNextFromGuests,
    // repeat booking blocking removed
  };

  const stepDateTimeProps = {
    selectedDate,
    selectedTimeSlot,
    showDatePicker,
    availableSlots,
    loadingSlots,
    bookingError,
    isWsConnected,
    submitLoading,
    onDateChange: handleDateChange,
    onShowDatePickerChange: setShowDatePicker,
    onTimeSlotSelect: async (slot) => {
      const newTimeSlot = slot.time.split(":").slice(0, 2).join(":");

      // Защита от повторного выбора того же слота
      if (selectedTimeSlot?.time === slot.time) {
        debugLog("Same slot selected, skipping");
        return;
      }

      // Разблокируем предыдущий слот, если был заблокирован другой
      if (lockedSlot && lockedSlot !== newTimeSlot) {
        debugLog("Unlocking previous slot before selecting new one");
        await unlockCurrentSlot();
      }

      // Отменяем pending блокировку если была
      if (lockPromiseRef.current) {
        lockPromiseRef.current.reject(new Error("Cancelled by user"));
        lockPromiseRef.current = null;
        pendingLockTimeRef.current = null;
      }

      setSelectedTimeSlot(slot);
      setSelectedStartTime(slot.time);
      setSelectedEndTime(null);
      setBookingError(null);
      loadAvailableEndTimes(slot.time);
    },
    onBack: async () => {
      await unlockCurrentSlot();
      setActiveStep(1);
    },
    onNext: handleNextFromTime,
    selectedStartTime,
    selectedEndTime,
    availableEndTimes,
    loadingEndTimes,
    freeTablesAvailable,
    suggestedEndTime,
    onEndTimeSelect: setSelectedEndTime,
    restaurant, // Передаем только restaurant
    restaurantSlug, // ← ДОБАВЛЕНО: передаем restaurantSlug
    // repeat booking blocking removed
  };

  const stepContactsProps = {
    userName,
    userPhone,
    wishes,
    guests,
    bookingError,
    submitLoading,
    onNameChange: handleNameChange,
    onPhoneChange: handlePhoneChange,
    onWishesChange: handleWishesChange,
    onBack: async () => {
      await unlockCurrentSlot();
      setActiveStep(2);
    },
    onBooking: handleBooking,
  };

  const stepSuccessProps = {
    restaurant,
    selectedTimeSlot,
    guests,
    userPhone,
    selectedDate,
    selectedStartTime,
    selectedEndTime,
    confirmedStartTime,
    confirmedEndTime,
    onClose: handleClose,
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div className={styles.overlay} onClick={handleClose}>
          <motion.div
            ref={modalRef}
            className={styles.modal}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.header}>
              <div className={styles.steps}>
                {[1, 2, 3, 4].map((s) => (
                  <React.Fragment key={s}>
                    <div
                      className={`${styles.step} ${
                        activeStep >= s ? styles.active : ""
                      }`}
                    >
                      <span>{s}</span>
                    </div>
                    {s < 4 && <div className={styles.stepLine} />}
                  </React.Fragment>
                ))}
              </div>
              <motion.button
                className={styles.closeButton}
                onClick={handleClose}
                whileTap={{ scale: 0.98 }}
              >
                <CloseIcon />
              </motion.button>
            </div>
            <div className={styles.body}>
              {activeStep === 1 && (
                <StepGuests {...stepGuestsProps} restaurantData={restaurant} />
              )}
              {activeStep === 2 && (
                <StepDateTime
                  {...stepDateTimeProps}
                  lastBookingTime={lastBookingTime}
                />
              )}
              {activeStep === 3 && <StepContacts {...stepContactsProps} />}
              {activeStep === 4 && <StepSuccess {...stepSuccessProps} />}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
