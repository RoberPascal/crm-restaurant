// components/Dashboard/Dashboard.jsx
"use client";

import { useEffect, useRef, useMemo, useCallback, useState } from "react";
import { useDashboard } from "@/context/DashboardContext";
import { formatDateForAPI } from "@/utils/date";
import BookingCard from "../BookingCard/BookingCard";
import DateSelector from "../DateSelector/DateSelector";
import { motion, AnimatePresence } from "framer-motion";
import styles from "./Dashboard.module.scss";
import { api } from "@/utils/api";
import dynamic from "next/dynamic";

// ОПТИМИЗАЦИЯ: Логирование только в dev-режиме
const IS_DEV = process.env.NODE_ENV === "development";
const debugLog = IS_DEV ? console.log.bind(console) : () => {};

// Динамический импорт BookingModal для избежания проблем с инициализацией
const BookingModal = dynamic(
  () => import("@/components/BookingModal/BookingModal"),
  {
    ssr: false,
    loading: () => null,
  },
);

const STATUS_CONFIG = {
  pending: { label: "Новые", color: "#fbbf24" },
  confirmed: { label: "Подтверждено", color: "#10b981" },
  assigned: { label: "Стол назначен", color: "#3b82f6" },
  arrived: { label: "Гости пришли", color: "#8b5cf6" },
  completed: { label: "Завершено", color: "#6b7280" },
  no_show: { label: "Не пришли", color: "#ef4444" },
  cancelled: { label: "Отменено", color: "#9ca3af" },
};

const TABLE_BLOCKING_STATUSES = new Set(["cancelled", "no_show"]);
const CONFIRMATION_STATUSES = [
  "confirmed",
  "assigned",
  "arrived",
  "pending_review",
];

const CustomSelect = ({
  options,
  value,
  onChange,
  placeholder = "Выберите статус",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const selectRef = useRef(null);

  const selectedOption = options.find((opt) => opt.value === value);
  const displayLabel = selectedOption?.label || placeholder;

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (selectRef.current && !selectRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={selectRef} className={styles.customSelect}>
      <button
        className={`${styles.selectTrigger} ${isOpen ? styles.open : ""}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className={styles.selectedLabel}>{displayLabel}</span>
        <motion.svg
          className={styles.arrow}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        >
          <polyline
            points="6 9 12 15 18 9"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </motion.svg>
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.ul
            className={styles.optionsList}
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.95 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            role="listbox"
          >
            {options.map((option) => (
              <li
                key={option.value}
                className={`${styles.optionItem} ${
                  value === option.value ? styles.selected : ""
                }`}
                onClick={() => {
                  onChange(option.value);
                  setIsOpen(false);
                }}
                role="option"
                aria-selected={value === option.value}
              >
                {option.label}
                {option.count > 0 && ` (${option.count})`}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
};

export default function Dashboard() {
  const {
    selectedDate,
    setDate,
    selectedRestaurantSlug,
    selectedRestaurantId,
    user,
    loading,
    setLoading,
    error,
    setError,
    restaurants,
    bookings,
    updateBookings,
    isAdmin,
    isOperator,
    canCreateBooking,
  } = useDashboard();

  const [isWsConnected, setIsWsConnected] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("");
  const [activeCardId, setActiveCardId] = useState(null);
  const [isBookingModalOpen, setIsBookingModalOpen] = useState(false);

  // Автоматически скрываем ошибку через 7 секунд
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), 7000);
    return () => clearTimeout(timer);
  }, [error, setError]);

  // ОПТИМИЗАЦИЯ: Debounce поиска чтобы не фильтровать на каждое нажатие клавиши
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const abortRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const wsTokenRef = useRef(null);
  const tokenFetchInProgressRef = useRef(false);
  const loadBookingsInProgressRef = useRef(false);

  const restaurant = useMemo(
    () => restaurants.find((r) => r.slug === selectedRestaurantSlug) || {},
    [restaurants, selectedRestaurantSlug],
  );

  const currentDateStr = useMemo(
    () => formatDateForAPI(selectedDate),
    [selectedDate],
  );

  // ОПТИМИЗАЦИЯ: ref для currentDateStr чтобы WS не переподключался при смене даты
  const currentDateStrRef = useRef(currentDateStr);
  useEffect(() => {
    currentDateStrRef.current = currentDateStr;
  }, [currentDateStr]);

  // ОПТИМИЗАЦИЯ: ref для bookings — передаётся в BookingCard вместо массива
  // чтобы React.memo не ломался от нового массива при каждом WS обновлении
  const bookingsRef = useRef(bookings);
  useEffect(() => {
    bookingsRef.current = bookings;
  }, [bookings]);

  const formatBooking = useCallback((b) => {
    const bookingData = b.booking || b;
    if (!bookingData.date) {
      debugLog("Бронь без даты:", bookingData);
      return null;
    }

    let suitableTables = bookingData.suitable_tables || [];
    if (
      (!suitableTables || suitableTables.length === 0) &&
      bookingData.suitable_tables_json
    ) {
      try {
        suitableTables = JSON.parse(bookingData.suitable_tables_json);
      } catch (e) {
        debugLog("Failed to parse suitable_tables_json:", e);
        suitableTables = [];
      }
    }

    return {
      ...bookingData,
      suitable_tables: suitableTables,
      suitable_tables_json: bookingData.suitable_tables_json,
      statusConfig: STATUS_CONFIG[bookingData.status?.toLowerCase()] || {
        label: bookingData.status || "Неизвестно",
        color: "#000",
      },
      displayTime: bookingData.time?.slice(0, 5) ?? "00:00",
      totalGuests: (bookingData.adults ?? 0) + (bookingData.children ?? 0),
      table_number: bookingData.table_number ?? null,
      name: bookingData.name || "Без имени",
      phone: bookingData.phone || "Без телефона",
      status: bookingData.status?.toLowerCase() || "unknown",
      // --- ДОБАВЛЕНО ---
      end_time: bookingData.end_time,
      reservation_end_time: bookingData.reservation_end_time,
      wishes: bookingData.wishes || null,
    };
  }, []);

  const stats = useMemo(() => {
    const totalGuests = bookings.reduce((sum, b) => {
      const guests = b.totalGuests || (b.adults || 0) + (b.children || 0);
      return sum + (isNaN(guests) ? 0 : guests);
    }, 0);

    const totalTables =
      typeof restaurant?.table_count === "number"
        ? restaurant.table_count
        : Array.isArray(restaurant?.tables) && restaurant.tables
          ? restaurant.tables.length
          : Number(restaurant?.tables) || 0;

    const occupiedTableIds = new Set();
    let confirmedBookings = 0;

    bookings.forEach((booking) => {
      const status = booking.status || "unknown";

      if (!TABLE_BLOCKING_STATUSES.has(status) && booking.table_number) {
        occupiedTableIds.add(String(booking.table_number));
      }

      if (CONFIRMATION_STATUSES.includes(status)) {
        confirmedBookings += 1;
      }
    });

    const tablesUsed = occupiedTableIds.size;

    const assignedBookings = bookings.filter(
      (b) => b.status === "assigned",
    ).length;

    const withoutPlacardBookings = bookings.filter(
      (b) => b.status === "assigned" && !b.cleaning_started_at,
    ).length;

    const safeTotalTables = totalTables || 0;

    const isInactive = (status) =>
      status === "completed" || status === "cancelled" || status === "no_show";

    const totalRequests = bookings.length;
    const activeRequests = bookings.filter((b) => !isInactive(b.status)).length;
    const withoutTable = bookings.filter(
      (b) => !isInactive(b.status) && !b.table_id && !b.table_number,
    ).length;

    return {
      totalBookings: totalRequests,
      totalGuests,
      tablesUsed,
      totalTables: safeTotalTables,
      assignedBookings,
      withoutPlacardBookings,
      kpis: {
        totalRequests,
        activeRequests,
        withoutTable,
      },
      tableUsage: {
        total: safeTotalTables,
        occupied: tablesUsed,
        confirmed: confirmedBookings,
        free: Math.max(safeTotalTables - tablesUsed, 0),
        waiting: Math.max(confirmedBookings - tablesUsed, 0),
        occupancyPercent:
          safeTotalTables > 0
            ? Math.min((tablesUsed / safeTotalTables) * 100, 100)
            : 0,
        confirmedPercent:
          safeTotalTables > 0
            ? Math.min(
                (Math.min(confirmedBookings, safeTotalTables) /
                  safeTotalTables) *
                  100,
                100,
              )
            : 0,
      },
    };
  }, [bookings, restaurant.table_count, restaurant.tables]);

  const countByStatus = useMemo(() => {
    return bookings.reduce((acc, b) => {
      acc[b.status] = (acc[b.status] || 0) + 1;
      return acc;
    }, {});
  }, [bookings]);

  const filteredBookings = useMemo(() => {
    let filtered = bookings;

    if (selectedStatus) {
      filtered = filtered.filter((b) => b.status === selectedStatus);
    }

    if (debouncedSearchQuery.trim()) {
      const q = debouncedSearchQuery.toLowerCase();
      filtered = filtered.filter(
        (b) =>
          b.name.toLowerCase().includes(q) ||
          b.phone.includes(debouncedSearchQuery),
      );
    }

    return filtered;
  }, [bookings, selectedStatus, debouncedSearchQuery]);

  const groupedBookings = useMemo(() => {
    const groups = {};

    filteredBookings.forEach((booking) => {
      // ДОБАВЛЕНО: надежная проверка displayTime
      const time = booking.displayTime || booking.time || "00:00";

      // ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: убедимся, что time - строка
      const timeString = typeof time === "string" ? time : "00:00";

      // БЕЗОПАСНЫЙ split с проверкой
      const timeParts = timeString.split(":");
      const hour = timeParts.length > 0 ? parseInt(timeParts[0]) || 0 : 0;

      const slotKey = `${String(hour).padStart(2, "0")}:00–${String(
        hour + 1,
      ).padStart(2, "0")}:00`;

      if (!groups[slotKey]) {
        groups[slotKey] = [];
      }
      groups[slotKey].push(booking);
    });

    return Object.entries(groups)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([slot, bookings]) => ({
        slot,
        bookings: bookings.sort((a, b) => {
          // Безопасная сортировка по времени
          const timeA = a.displayTime || a.time || "00:00";
          const timeB = b.displayTime || b.time || "00:00";
          return timeA.localeCompare(timeB);
        }),
      }));
  }, [filteredBookings]);

  const updateBookingStatus = useCallback(
    async (bookingId, newStatus) => {
      if (newStatus === "pending") return;

      try {
        const updatedBooking = await api.patch(
          `/api/v1/admin/bookings/${bookingId}/status`,
          { status: newStatus },
        );

        const formatted = formatBooking(updatedBooking);

        updateBookings((prev) =>
          prev.map((b) => (b.id === formatted.id ? formatted : b)),
        );
      } catch (err) {
        console.error("Ошибка обновления статуса:", err);
        setError(err.message || "Не удалось обновить статус");
      }
    },
    [formatBooking, updateBookings, setError],
  );

  // Stable callbacks for BookingCard (prevent re-renders from inline arrows)
  const handleCardToggle = useCallback((bookingId) => {
    setActiveCardId((prev) => (prev === bookingId ? null : bookingId));
  }, []);

  const handleBookingDeleted = useCallback(() => {
    setIsBookingModalOpen(false);
  }, []);

  const getWsToken = useCallback(async (retryCount = 0) => {
    if (wsTokenRef.current && !isTokenExpired(wsTokenRef.current)) {
      return wsTokenRef.current;
    }

    if (tokenFetchInProgressRef.current) {
      if (retryCount >= 30) {
        // Max ~3 seconds waiting (30 * 100ms)
        tokenFetchInProgressRef.current = false;
        throw new Error("WS token fetch timeout");
      }
      await new Promise((r) => setTimeout(r, 100));
      return getWsToken(retryCount + 1);
    }

    tokenFetchInProgressRef.current = true;
    try {
      const response = await api.get("/api/v1/admin/auth/ws-token");

      if (!response || !response.access_token) {
        throw new Error("Invalid WS token response");
      }

      wsTokenRef.current = response.access_token;
      return response.access_token;
    } catch (error) {
      console.error("Ошибка получения WS токена:", error);

      if (error.status === 403) {
        try {
          await api.get("/api/v1/admin/auth/renew-csrf");
          const response = await api.get("/api/v1/admin/auth/ws-token");
          if (response && response.access_token) {
            wsTokenRef.current = response.access_token;
            return response.access_token;
          }
        } catch (retryError) {
          console.error("Retry failed:", retryError);
        }
      }

      throw error;
    } finally {
      tokenFetchInProgressRef.current = false;
    }
  }, []);

  const isTokenExpired = (token) => {
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      return Date.now() >= payload.exp * 1000 - 60_000;
    } catch {
      return true;
    }
  };

  const loadBookings = useCallback(
    async (force = false, dateStr = currentDateStr) => {
      if (!selectedRestaurantId || !selectedDate) {
        return;
      }

      if (loadBookingsInProgressRef.current && !force) {
        return;
      }

      loadBookingsInProgressRef.current = true;
      setLoading(true);
      setError(null);

      try {
        if (abortRef.current) abortRef.current.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        const data = await api.get(
          `/api/v1/admin/bookings/?restaurant_id=${selectedRestaurantId}&date=${dateStr}`,
          { signal: controller.signal },
        );

        let bookingsArray = [];

        if (Array.isArray(data)) {
          bookingsArray = data;
        } else if (data && typeof data === "object") {
          if (Array.isArray(data.bookings)) {
            bookingsArray = data.bookings;
          } else if (Array.isArray(data.data)) {
            bookingsArray = data.data;
          } else if (data.data && Array.isArray(data.data.bookings)) {
            bookingsArray = data.data.bookings;
          }
        }

        const formatted = bookingsArray.map(formatBooking).filter(Boolean);
        updateBookings(formatted);
      } catch (err) {
        if (err.name !== "AbortError") {
          console.error("Ошибка loadBookings:", err);
          setError(err.message || "Не удалось загрузить брони");
        }
      } finally {
        setLoading(false);
        loadBookingsInProgressRef.current = false;
      }
    },
    [
      selectedRestaurantId,
      selectedDate,
      currentDateStr,
      // ИСПРАВЛЕНО: убран bookings.length из зависимостей — он вызывал пересоздание колбэка при каждом обновлении
      formatBooking,
      setLoading,
      setError,
      updateBookings,
    ],
  );

  useEffect(() => {
    if (
      selectedRestaurantId &&
      selectedDate &&
      !loadBookingsInProgressRef.current
    ) {
      loadBookings(true);
    }
  }, [selectedRestaurantId, selectedDate, loadBookings]);

  const handleDateChange = useCallback(
    (newDate) => {
      setDate(newDate);
      // ОПТИМИЗАЦИЯ: WS больше не переподключается при смене даты (используем ref),
      // поэтому ручное закрытие не нужно
      const newDateStr = formatDateForAPI(newDate);
      loadBookings(true, newDateStr);
    },
    [setDate, loadBookings],
  );

  useEffect(() => {
    if (!selectedRestaurantSlug || !selectedRestaurantId) return;

    let cancelled = false;
    let reconnectAttempts = 0;
    const MAX_RECONNECT = 15; // ИСПРАВЛЕНО: было 3, WS умирал после 3 ошибок
    const BASE_DELAY = 2000;

    const connect = async () => {
      if (cancelled || reconnectAttempts >= MAX_RECONNECT) return;

      if (wsRef.current) {
        wsRef.current.close(1000, "Reconnecting");
        wsRef.current = null;
      }

      try {
        const token = await getWsToken();
        if (cancelled) return;

        const API_BASE = process.env.NEXT_PUBLIC_API_URL;
        const protocol = API_BASE.startsWith("https") ? "wss" : "ws";
        const host = API_BASE.replace(/^https?:\/\//, "");
        const wsUrl = `${protocol}://${host}/ws/crm/bookings/${selectedRestaurantSlug}?token=${encodeURIComponent(
          token,
        )}`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setIsWsConnected(true);
          setError(null);
          reconnectAttempts = 0;
        };

        ws.onclose = (e) => {
          setIsWsConnected(false);
          wsRef.current = null;
          if (e.code === 1000 || cancelled) return;
          if (!cancelled && reconnectAttempts < MAX_RECONNECT) {
            reconnectAttempts++;
            const delay = Math.min(
              BASE_DELAY * Math.pow(2, reconnectAttempts),
              30_000,
            );
            reconnectTimeoutRef.current = setTimeout(connect, delay);
          }
        };

        ws.onerror = () => setIsWsConnected(false);

        ws.onmessage = (evt) => {
          if (evt.data === "ping") return ws.send("pong");
          if (evt.data === "pong") return;

          let data;
          try {
            data = JSON.parse(evt.data);
          } catch {
            return;
          }

          debugLog("WebSocket message received:", data.type);

          if (data.type === "connection_established") return;

          const bookingData = data.booking || data;
          if (!bookingData?.date) {
            return;
          }

          let bookingDateStr;
          if (typeof bookingData.date === "string") {
            bookingDateStr = bookingData.date.split("T")[0];
          } else {
            bookingDateStr = formatDateForAPI(new Date(bookingData.date));
          }

          if (bookingDateStr !== currentDateStrRef.current) {
            return;
          }

          const formatted = formatBooking(bookingData);
          if (!formatted) {
            return;
          }

          if (
            data.type === "booking_created" ||
            data.type === "booking_update"
          ) {
            debugLog("Processing booking event:", data.type, formatted.id);
            updateBookings((prev) => {
              const exists = prev.some((b) => b.id === formatted.id);
              if (exists) {
                return prev.map((b) => (b.id === formatted.id ? formatted : b));
              }
              return [formatted, ...prev];
            });
          } else if (data.type === "booking_deleted") {
            const id = data.booking_id ?? data.booking?.id;
            updateBookings((prev) => prev.filter((b) => b.id !== id));
          }
        };
      } catch (err) {
        console.error("Ошибка WS:", err.message);
        setIsWsConnected(false);
        if (!cancelled && reconnectAttempts < MAX_RECONNECT) {
          reconnectAttempts++;
          const delay = Math.min(
            BASE_DELAY * Math.pow(2, reconnectAttempts),
            30_000,
          );
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        }
      }
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimeoutRef.current)
        clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.close(1000, "Component unmount");
        wsRef.current = null;
      }
      setIsWsConnected(false);
    };
  }, [
    selectedRestaurantSlug,
    selectedRestaurantId,
    // ОПТИМИЗАЦИЯ: currentDateStr убран из deps — используем ref чтобы WS не переподключался при смене даты
    formatBooking,
    updateBookings,
    setError,
    getWsToken,
  ]);

  // ОПТИМИЗАЦИЯ: Убрано тяжёлое логирование всего состояния на каждое изменение

  // ОПТИМИЗАЦИЯ: мемоизируем statusOptions чтобы не создавать массив на каждом рендере
  const statusOptions = useMemo(
    () => [
      { value: null, label: "Все статусы" },
      ...Object.entries(STATUS_CONFIG).map(([key, config]) => ({
        value: key,
        label: config.label,
        count: countByStatus[key] || 0,
      })),
    ],
    [countByStatus],
  );

  if (restaurants.length === 0 && !loading) {
    return <div className={styles.empty}>Нет ресторанов</div>;
  }

  if (!selectedRestaurantSlug) {
    return <div className={styles.loading}>Выберите ресторан...</div>;
  }

  return (
    <div className={styles.dashboard}>
      {error && (
        <div className={styles.errorBanner} role="alert">
          <span>{error}</span>
          <button onClick={() => setError(null)} aria-label="Закрыть">
            ×
          </button>
        </div>
      )}
      <div className={styles.header}>
        <div className={styles.headerMain}>
          <div className={styles.controls}>
            <DateSelector
              selectedDate={selectedDate}
              onDateChange={handleDateChange}
              isLoading={loading}
            />
          </div>
        </div>

        <div className={styles.statsBar}>
          <div className={styles.quickStats}>
            {[
              {
                label: "Всего",
                value: stats.kpis?.totalRequests ?? 0,
                hint: "Всего заявок на день",
              },
              {
                label: "Активные",
                value: stats.kpis?.activeRequests ?? 0,
                hint: "Все, кроме завершённых/отменённых/не пришли",
              },
              {
                label: "Без стола",
                value: stats.kpis?.withoutTable ?? 0,
                hint: "Активные заявки без назначенного стола",
              },
            ].map(({ label, value, hint }) => (
              <div
                key={label}
                className={styles.statChip}
                title={hint || undefined}
              >
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.filtersRow}>
        <input
          type="text"
          placeholder="Поиск по имени или телефону..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className={styles.searchInput}
        />

        <CustomSelect
          options={statusOptions}
          value={selectedStatus}
          onChange={setSelectedStatus}
          placeholder="Все статусы"
        />
      </div>

      <main className={styles.main}>
        {loading && (
          <div className={styles.loadingOverlay}>
            <div className={styles.loadingSpinner}>
              <div className={styles.spinner}></div>
              <p>Загрузка броней...</p>
            </div>
          </div>
        )}
        {groupedBookings.length === 0 && !loading ? (
          <div className={styles.emptyState}>
            <h3>Нет броней</h3>
            <p>
              {searchQuery || selectedStatus
                ? "По вашему запросу ничего не найдено"
                : "На выбранную дату броней нет"}
            </p>
            {isWsConnected && (
              <p className={styles.liveIndicator}>Ожидаем новые брони...</p>
            )}
          </div>
        ) : (
          <div className={styles.timeSlots}>
            {groupedBookings.map(({ slot, bookings: slotBookings }) => {
              return (
                <div key={slot} className={styles.timeSlot}>
                  <div className={styles.slotBookings}>
                    {slotBookings.map((booking) => (
                      <BookingCard
                        key={booking.id}
                        booking={booking}
                        userRole={user?.role}
                        isOpen={activeCardId === booking.id}
                        onToggle={handleCardToggle}
                        updateBookings={updateBookings}
                        onStatusChange={updateBookingStatus}
                        setError={setError}
                        onBookingDeleted={handleBookingDeleted}
                        restaurantSchedule={restaurant?.schedule}
                        allBookingsRef={bookingsRef}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {canCreateBooking && (
        <motion.button
          className={styles.addBookingBtn}
          onClick={() => setIsBookingModalOpen(true)}
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.95 }}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          exit={{ scale: 0 }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 5V19M5 12H19"
              stroke="white"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </motion.button>
      )}

      {canCreateBooking && (
        <BookingModal
          isOpen={isBookingModalOpen}
          onClose={() => setIsBookingModalOpen(false)}
          restaurant={restaurant}
          restaurantSlug={selectedRestaurantSlug}
          onBookingCreated={() => {
            loadBookings(true);
          }}
          onBookingDeleted={() => {
            setIsBookingModalOpen(false);
            loadBookings(true);
          }}
        />
      )}
    </div>
  );
}
