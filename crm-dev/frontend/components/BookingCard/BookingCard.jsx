"use client";

import { useState, useMemo, useEffect, useCallback, memo } from "react";
import styles from "./BookingCard.module.scss";
import { api } from "@/utils/api";

// ОПТИМИЗАЦИЯ: Логирование только в dev-режиме
const IS_DEV = process.env.NODE_ENV === "development";
const debugLog = IS_DEV ? console.log.bind(console) : () => {};

// Конфигурации статусов
const STATUS_CONFIG = {
  pending: {
    label: "Новая заявка",
    color: "#fbbf24",
    bgColor: "#fef3c7",
    available: ["confirmed", "assigned", "cancelled"],
  },
  confirmed: {
    label: "Подтверждено",
    color: "#10b981",
    bgColor: "#d1fae5",
    available: ["arrived", "no_show", "cancelled"],
  },
  assigned: {
    label: "Стол назначен",
    color: "#3b82f6",
    bgColor: "#dbeafe",
    available: ["arrived", "no_show", "cancelled", "completed"],
  },
  arrived: {
    label: "Гости пришли",
    color: "#8b5cf6",
    bgColor: "#ede9fe",
    available: ["completed", "no_show"],
  },
  completed: {
    label: "Завершено",
    color: "#6b7280",
    bgColor: "#f3f4f6",
    available: [],
  },
  no_show: {
    label: "Не пришли",
    color: "#ef4444",
    bgColor: "#fee2e2",
    available: [],
  },
  cancelled: {
    label: "Отменено",
    color: "#9ca3af",
    bgColor: "#f3f4f6",
    available: [],
  },
};

const COMPLETED_STATUSES = ["completed", "cancelled", "no_show"];

// Вспомогательные функции
const safeParseJSON = (str, fallback = []) => {
  if (!str) return fallback;
  try {
    return JSON.parse(str);
  } catch {
    return fallback;
  }
};

const normalizeTablesPayload = (tables) => {
  if (!Array.isArray(tables)) return [];

  return tables
    .map((table) => {
      if (!table) return null;

      if (typeof table === "number") {
        return {
          id: table,
          number: String(table),
        };
      }

      if (typeof table === "object") {
        const normalized = { ...table };
        if (normalized.number == null && normalized.table_number != null) {
          normalized.number = normalized.table_number;
        }
        return normalized;
      }

      return null;
    })
    .filter(Boolean);
};

const formatTime = (timeValue) => {
  if (!timeValue) return "—";

  // Если это строка времени в формате "HH:MM:SS" или "HH:MM"
  if (typeof timeValue === "string" && timeValue.includes(":")) {
    // Если строка содержит дату и время в формате "YYYY-MM-DDTHH:MM"
    if (timeValue.includes("T") && timeValue.length > 10) {
      try {
        // Извлекаем только время после "T"
        const timePart = timeValue.split("T")[1];
        if (timePart) {
          const timeParts = timePart.split(":");
          if (timeParts.length >= 2) {
            const hours = timeParts[0].padStart(2, "0");
            const minutes = timeParts[1].padStart(2, "0");
            return `${hours}:${minutes}`;
          }
        }
      } catch (e) {
        // T datetime parse fallback
      }
    }

    // Если строка содержит дату и время (формат "YYYY-MM-DD HH:MM:SS")
    if (timeValue.includes(" ")) {
      try {
        const timePart = timeValue.split(" ")[1];
        if (timePart) {
          const timeParts = timePart.split(":");
          if (timeParts.length >= 2) {
            const hours = timeParts[0].padStart(2, "0");
            const minutes = timeParts[1].padStart(2, "0");
            return `${hours}:${minutes}`;
          }
        }
      } catch (e) {
        // datetime parse fallback
      }
    }

    // Если это просто время "HH:MM:SS" или "HH:MM"
    const timeParts = timeValue.split(":");
    if (timeParts.length >= 2) {
      const hours = timeParts[0].padStart(2, "0");
      const minutes = timeParts[1].padStart(2, "0");
      return `${hours}:${minutes}`;
    }

    return timeValue.length > 5 ? timeValue.substring(0, 5) : timeValue;
  }

  // Если это DateTime объект
  if (timeValue instanceof Date) {
    return timeValue.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return "—";
};

const getEndTime = (booking) => {
  // Проверяем все возможные поля с временем окончания в порядке приоритета
  if (booking.end_datetime) return booking.end_datetime;
  if (booking.end_time) return booking.end_time;
  if (booking.reservation_end_time) return booking.reservation_end_time;
  if (booking.endTime) return booking.endTime;
  if (booking.reservationEndTime) return booking.reservationEndTime;

  // Если нет времени окончания - это означает "до закрытия"
  return null;
};

const getClosingTime = (booking, restaurantSchedule) => {
  if (
    !booking.date ||
    !restaurantSchedule ||
    !Array.isArray(restaurantSchedule)
  ) {
    return null;
  }

  try {
    const bookingDate = new Date(booking.date);
    const dayOfWeek = bookingDate.getDay(); // 0-6 (воскресенье-суббота)

    // Находим расписание для этого дня недели
    const daySchedule = restaurantSchedule.find(
      (schedule) => schedule.day === dayOfWeek,
    );

    // Проверяем различные возможные форматы времени закрытия
    if (daySchedule) {
      const closeTime =
        daySchedule.close || daySchedule.close_time || daySchedule.end;
      if (closeTime) {
        return closeTime; // Возвращаем время закрытия, например "02:00"
      }
    }

    return null;
  } catch (error) {
    console.error("Error getting closing time:", error);
    return null;
  }
};

const formatGuests = (booking) => {
  const adults = booking.adults || booking.totalGuests || 0;
  const children = booking.children || 0;
  if (children <= 0) return `${adults} чел`;
  return `${adults} взр. + ${children} реб.`;
};

const getTableTooltip = (table) => {
  const parts = [];
  if (table.seats_min && table.seats_max) {
    parts.push(`${table.seats_min}-${table.seats_max} мест`);
  }
  if (table.location_mark) {
    parts.push(table.location_mark);
  }
  if (table.features?.length > 0) {
    parts.push(table.features.join(", "));
  }
  return parts.join(" • ") || `Стол ${table.number}`;
};

// ОПТИМИЗАЦИЯ: Обёрнуто в React.memo для предотвращения лишних ре-рендеров
const BookingCard = memo(function BookingCard({
  booking,
  onStatusChange,
  userRole,
  style,
  isOpen,
  onToggle,
  updateBookings,
  setError,
  onBookingDeleted,
  restaurantSchedule,
  allBookingsRef, // ОПТИМИЗАЦИЯ: ref вместо массива — не ломает React.memo
}) {
  const [isUpdating, setIsUpdating] = useState(false);
  const [minutesUntilEnd, setMinutesUntilEnd] = useState(null);
  const [availableTables, setAvailableTables] = useState([]);
  const [showTableSelection, setShowTableSelection] = useState(false);

  const canManage = !!userRole && userRole !== "guest";
  const isBookingActive = !COMPLETED_STATUSES.includes(booking.status);
  const statusCfg = STATUS_CONFIG[booking.status] || {
    label: booking.status,
    color: "#adb5bd",
    bgColor: "#e9ecef",
  };

  // Получаем время начала и окончания
  const startTime = formatTime(booking.time || booking.start_datetime);
  const endTime = getEndTime(booking);
  const isUntilClosing = !endTime || endTime === null || endTime === undefined;

  // Получаем реальное время закрытия
  const closingTime = getClosingTime(booking, restaurantSchedule);

  // Форматируем интервал времени для отображения
  const timeRange = isUntilClosing
    ? closingTime
      ? `${startTime} - ${formatTime(closingTime)}`
      : `${startTime} - до закрытия`
    : `${startTime} - ${formatTime(endTime)}`;

  // Проверяем, есть ли уведомление об опоздании
  const isDelayed =
    booking.delay_notified === true || booking.is_delayed === true;

  // Функция для проверки, занят ли стол в это время (с учетом пересечения интервалов)
  // ОПТИМИЗАЦИЯ: используем allBookingsRef.current вместо пропа allBookings
  const isTableOccupied = useCallback(
    (tableId) => {
      const allBookings = allBookingsRef?.current;
      if (!allBookings || !Array.isArray(allBookings)) return false;

      const currentBookingTime = booking.time || booking.start_datetime;
      const currentBookingDate = booking.date;

      if (!currentBookingTime || !currentBookingDate) return false;

      // Парсим время начала текущей брони
      const parseTime = (timeVal) => {
        if (!timeVal) return null;
        if (timeVal instanceof Date) {
          return timeVal.getHours() * 60 + timeVal.getMinutes();
        }
        if (typeof timeVal === "string") {
          let t = timeVal;
          if (t.includes("T")) t = t.split("T")[1];
          if (t.includes(" ")) t = t.split(" ")[1];
          const [h, m] = t.split(":").map(Number);
          return h * 60 + m;
        }
        return null;
      };

      const currentStartMinutes = parseTime(currentBookingTime);
      if (currentStartMinutes === null) return false;

      // Определяем длительность (по умолчанию 1ч 45м = 105 мин, как на бэке)
      const getDuration = (b) => {
        if (b.end_time || b.end_datetime || b.endTime || b.reservationEndTime) {
          const start = parseTime(b.time || b.start_datetime);
          const end = parseTime(
            b.end_time || b.end_datetime || b.endTime || b.reservationEndTime,
          );
          if (start !== null && end !== null) {
            let duration = end - start;
            if (duration < 0) duration += 24 * 60; // Переход через полночь
            return duration;
          }
        }
        return 105; // 1 час 45 минут стандарт
      };

      const currentDuration = getDuration(booking);
      const currentEndMinutes = currentStartMinutes + currentDuration;

      // Ищем другие брони на этот же стол, пересекающиеся по времени
      const conflictingBooking = allBookings.find((otherBooking) => {
        // Пропускаем текущую бронь
        if (otherBooking.id === booking.id) return false;

        // Проверяем статус (только активные)
        if (COMPLETED_STATUSES.includes(otherBooking.status)) return false;

        // Проверяем, назначен ли этому столу другой стол
        if (otherBooking.table_id !== tableId) return false;

        // Проверяем, что дата совпадает
        // (упрощено, предполагается, что allBookings уже отфильтрованы по дате)
        if (
          otherBooking.date &&
          currentBookingDate &&
          otherBooking.date !== currentBookingDate
        )
          return false;

        // Проверяем пересечение времени
        const otherStartMinutes = parseTime(
          otherBooking.time || otherBooking.start_datetime,
        );
        if (otherStartMinutes === null) return false;

        const otherDuration = getDuration(otherBooking);
        const otherEndMinutes = otherStartMinutes + otherDuration;

        // Добавляем буфер 15 минут (как на бэке)
        const BUFFER = 15;

        // Логика пересечения:
        // (StartA < EndB + Buffer) AND (EndA + Buffer > StartB)
        const isOverlapping =
          currentStartMinutes < otherEndMinutes + BUFFER &&
          currentEndMinutes + BUFFER > otherStartMinutes;

        return isOverlapping;
      });

      return !!conflictingBooking;
    },
    [
      booking.id,
      booking.time,
      booking.start_datetime,
      booking.date,
      booking.end_time,
      booking.end_datetime,
      allBookingsRef,
    ],
  );

  const isTableSelectable = useCallback(
    (table) => {
      if (!table || typeof table !== "object") return false;
      if (typeof table.is_available === "boolean") {
        return table.is_available;
      }
      if (
        typeof table.capacity_ok === "boolean" &&
        table.capacity_ok === false
      ) {
        return false;
      }
      if (
        typeof table.is_conflicting === "boolean" &&
        table.is_conflicting === true
      ) {
        return false;
      }
      if (table.id == null) return false;
      return !isTableOccupied(table.id);
    },
    [isTableOccupied],
  );

  const selectableTablesCount = useMemo(
    () => availableTables.filter((table) => isTableSelectable(table)).length,
    [availableTables, isTableSelectable],
  );

  const totalTablesCount = availableTables.length;

  // Stable reference for suitable_tables to avoid refetching on every WS update
  const suitableTablesKey = useMemo(
    () =>
      JSON.stringify(
        booking.suitable_tables || booking.suitable_tables_json || [],
      ),
    [booking.suitable_tables, booking.suitable_tables_json],
  );

  // Загрузка доступных столов — ОПТИМИЗАЦИЯ: только когда карточка открыта
  useEffect(() => {
    if (!isBookingActive || !isOpen) return;

    const abortController = new AbortController();

    const loadTables = async () => {
      try {
        const response = await api.get(
          `/api/v1/admin/bookings/${booking.id}/suitable-tables`,
        );
        if (abortController.signal.aborted) return;
        let normalized = [];
        if (response?.all_tables?.length) {
          normalized = normalizeTablesPayload(response.all_tables);
        } else if (response?.suitable_tables?.length) {
          normalized = normalizeTablesPayload(response.suitable_tables);
        }

        if (normalized.length > 0) {
          setAvailableTables(normalized);
        } else {
          const tables =
            booking.suitable_tables?.length > 0
              ? normalizeTablesPayload(booking.suitable_tables)
              : normalizeTablesPayload(
                  safeParseJSON(booking.suitable_tables_json, []),
                );
          setAvailableTables(tables);
        }
      } catch (error) {
        if (abortController.signal.aborted) return;
        console.error("Error loading tables:", error);
        const tables =
          booking.suitable_tables?.length > 0
            ? normalizeTablesPayload(booking.suitable_tables)
            : normalizeTablesPayload(
                safeParseJSON(booking.suitable_tables_json, []),
              );
        setAvailableTables(tables);
      }
    };

    loadTables();
    return () => abortController.abort();
  }, [booking.id, suitableTablesKey, isBookingActive, isOpen]);

  // Таймер до конца брони (только если есть конкретное время окончания)
  useEffect(() => {
    if (!isOpen || isUntilClosing) return;

    const updateTimer = () => {
      const now = new Date();
      let endTimeDate = new Date(endTime);

      // Если endTime – строка вида "HH:MM" или "HH:MM:SS", парсим вручную с датой брони
      if (isNaN(endTimeDate.getTime()) && typeof endTime === "string") {
        const dateStr = booking.date
          ? typeof booking.date === "string"
            ? booking.date.split("T")[0]
            : new Date(booking.date).toISOString().split("T")[0]
          : new Date().toISOString().split("T")[0];
        endTimeDate = new Date(`${dateStr}T${endTime}`);
      }

      if (isNaN(endTimeDate.getTime())) return;

      const diff = Math.floor((endTimeDate - now) / (1000 * 60));
      setMinutesUntilEnd(diff > 0 ? diff : 0);
    };

    updateTimer();
    const interval = setInterval(updateTimer, 60000);
    return () => clearInterval(interval);
  }, [isOpen, endTime, isUntilClosing, booking.date]);

  const availableStatusActions = useMemo(() => {
    if (!canManage) return [];
    return (STATUS_CONFIG[booking.status]?.available || []).map(
      (statusKey) => ({
        key: statusKey,
        label: STATUS_CONFIG[statusKey]?.label || statusKey,
        color: STATUS_CONFIG[statusKey]?.color || "#000",
        bgColor: STATUS_CONFIG[statusKey]?.bgColor || "#fff",
      }),
    );
  }, [booking.status, canManage]);

  const handleStatusUpdate = async (newStatus) => {
    if (!canManage || isUpdating) return;

    setIsUpdating(true);
    try {
      // Delegate status update to parent (Dashboard.updateBookingStatus)
      // which handles the API call and state update
      await onStatusChange?.(booking.id, newStatus);
    } catch (error) {
      console.error("Status update error:", error);
      setError?.(error.message || "Не удалось обновить статус");
    } finally {
      setIsUpdating(false);
    }
  };

  // Минимальный форматер, синхронный с Dashboard.formatBooking для консистентности
  const formatBookingLite = useCallback((b) => {
    const bookingData = b?.booking || b || {};
    return {
      ...bookingData,
      status:
        bookingData.status?.toLowerCase?.() || bookingData.status || "unknown",
      displayTime:
        bookingData.time?.slice?.(0, 5) ?? bookingData.time ?? "00:00",
      totalGuests: (bookingData.adults ?? 0) + (bookingData.children ?? 0),
      table_number: bookingData.table_number ?? null,
      name: bookingData.name || "Без имени",
      phone: bookingData.phone || "Без телефона",
      end_time: bookingData.end_time,
      reservation_end_time: bookingData.reservation_end_time,
      suitable_tables: bookingData.suitable_tables || [],
      suitable_tables_json: bookingData.suitable_tables_json,
    };
  }, []);

  const handleTableAssign = async (tableId) => {
    if (!canManage || isUpdating) return;

    setIsUpdating(true);
    try {
      const updated = await api.post(
        `/api/v1/admin/bookings/${booking.id}/assign-table`,
        {
          table_id: tableId,
        },
      );
      if (updateBookings && updated) {
        const formatted = formatBookingLite(updated);
        updateBookings((prev) =>
          Array.isArray(prev)
            ? prev.map((b) => (b.id === formatted.id ? formatted : b))
            : prev,
        );
      }
      setShowTableSelection(false);
    } catch (error) {
      console.error("Table assignment error:", error);
      setError?.(error.message || "Не удалось назначить стол");
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (
      !canManage ||
      !confirm("Удалить бронирование? Это действие нельзя отменить.")
    )
      return;

    setIsUpdating(true);
    try {
      await api.delete(`/api/v1/admin/bookings/${booking.id}`);
      await onBookingDeleted?.();
      if (updateBookings) {
        updateBookings((prev) =>
          Array.isArray(prev) ? prev.filter((b) => b.id !== booking.id) : prev,
        );
      }
    } catch (error) {
      console.error("Delete error:", error);
      setError?.(error.message || "Не удалось удалить бронирование");
    } finally {
      setIsUpdating(false);
    }
  };

  const handleRefreshTables = async () => {
    try {
      const response = await api.get(
        `/api/v1/admin/bookings/${booking.id}/suitable-tables`,
      );
      if (response?.all_tables?.length) {
        setAvailableTables(normalizeTablesPayload(response.all_tables));
      } else if (response?.suitable_tables?.length) {
        setAvailableTables(normalizeTablesPayload(response.suitable_tables));
      }
    } catch (error) {
      console.error("Error refreshing tables:", error);
    }
  };

  const tableDisplay = useMemo(() => {
    // 1. Prefer table_number from backend (resolved table name)
    if (booking.table_number != null) return booking.table_number;

    // 2. Try to look up from loaded available tables
    const tableId = booking.table_id;
    if (tableId != null && availableTables.length > 0) {
      const found = availableTables.find((t) => {
        const id = t?.id ?? t?.table_id;
        return id != null && id === tableId;
      });
      if (found?.number != null) return found.number;
    }

    // 3. Never fall back to table_id — it's a DB primary key, not a human-readable number
    return null;
  }, [booking.table_id, booking.table_number, availableTables]);

  return (
    <article
      className={`${styles.card} ${isOpen ? styles.active : ""} ${
        isUpdating ? styles.updating : ""
      }`}
      style={style}
    >
      {/* Компактный заголовок */}
      <div
        className={styles.compact}
        onClick={() => !isUpdating && onToggle?.(booking.id)}
      >
        <div
          className={styles.statusDot}
          style={{ backgroundColor: statusCfg.color }}
        />

        <div className={styles.mainInfo}>
          <div className={styles.timeRange}>{timeRange}</div>
          <div className={styles.guestLine}>
            <span className={styles.name}>{booking.name}</span>
            <span className={styles.separator}>•</span>
            <span className={styles.guests}>{formatGuests(booking)}</span>
          </div>
        </div>

        <div className={styles.badges}>
          {tableDisplay != null && (
            <span className={styles.table}>#{tableDisplay}</span>
          )}
          {isDelayed && (
            <span
              className={styles.delayBadge}
              title="Гость сообщил об опоздании"
            >
              ⏰
            </span>
          )}
          {!isUntilClosing &&
            minutesUntilEnd !== null &&
            minutesUntilEnd > 0 &&
            minutesUntilEnd <= 30 && (
              <span className={styles.timerTag}>{minutesUntilEnd}м</span>
            )}
        </div>

        <span
          className={styles.currentStatus}
          style={{ color: statusCfg.color, backgroundColor: statusCfg.bgColor }}
        >
          {statusCfg.label}
        </span>

        <a
          href={`tel:${booking.phone}`}
          className={styles.phone}
          onClick={(e) => e.stopPropagation()}
          title={booking.phone}
        >
          📞
        </a>
      </div>

      {/* Детали карточки */}
      {isOpen && (
        <div className={styles.details} onClick={(e) => e.stopPropagation()}>
          {/* Информация о времени */}
          {(isUntilClosing || isDelayed) && (
            <div className={styles.section}>
              {isUntilClosing && (
                <div className={styles.infoNote}>
                  📅 Бронь до закрытия
                  {closingTime && (
                    <span className={styles.noteDetail}>
                      {` (${formatTime(closingTime)})`}
                    </span>
                  )}
                </div>
              )}
              {isDelayed && (
                <div className={styles.warningNote}>
                  ⏰ Гость сообщил об опоздании
                </div>
              )}
            </div>
          )}

          {/* Управление столами */}
          {canManage && isBookingActive && (
            <div className={styles.section}>
              <div className={styles.sectionHeader}>
                <h4>Столы</h4>
                {!showTableSelection && totalTablesCount > 0 && (
                  <span className={styles.tableCounter}>
                    {selectableTablesCount}/{totalTablesCount}
                  </span>
                )}
              </div>

              {!showTableSelection ? (
                <div className={styles.tableManagement}>
                  <div className={styles.actionsRow}>
                    <button
                      onClick={() => setShowTableSelection(true)}
                      className={styles.primaryButton}
                      disabled={isUpdating}
                    >
                      {tableDisplay
                        ? `Изменить (сейчас #${tableDisplay})`
                        : "Выбрать стол"}
                    </button>
                    <button
                      onClick={handleRefreshTables}
                      className={styles.iconButton}
                      disabled={isUpdating}
                      title="Обновить"
                    >
                      🔄
                    </button>
                  </div>
                </div>
              ) : (
                <div className={styles.tableSelection}>
                  {availableTables.length > 0 ? (
                    <>
                      <div className={styles.tablesGrid}>
                        {availableTables.map((table) => {
                          if (!table) return null;

                          const tableId = table.id ?? table.table_id;
                          const selectable = isTableSelectable(table);
                          const isCurrentTable = tableId === booking.table_id;
                          const conflictFlag =
                            typeof table.is_conflicting === "boolean"
                              ? table.is_conflicting
                              : !selectable &&
                                tableId !== null &&
                                isTableOccupied(tableId);
                          const capacityIssue =
                            typeof table.capacity_ok === "boolean" &&
                            table.capacity_ok === false;
                          const restrictionReason = !selectable
                            ? table.status_reason ||
                              (capacityIssue ? "capacity" : null) ||
                              (conflictFlag ? "conflict" : null)
                            : null;

                          const titleMessage = !selectable
                            ? restrictionReason === "capacity"
                              ? "Стол не подходит по вместимости"
                              : "Стол уже занят другой бронью в это время"
                            : getTableTooltip(table);

                          return (
                            <button
                              key={`table-${
                                tableId ?? table.number ?? "fallback"
                              }`}
                              onClick={() =>
                                selectable &&
                                tableId != null &&
                                handleTableAssign(tableId)
                              }
                              disabled={
                                isUpdating || !selectable || tableId == null
                              }
                              className={`${styles.tableButton} ${
                                isCurrentTable ? styles.current : ""
                              } ${!selectable ? styles.occupied : ""}`}
                              title={titleMessage}
                            >
                              <div className={styles.tableNumber}>
                                #{table.number || tableId}
                              </div>
                              <div className={styles.tableInfo}>
                                {table.seats_min && table.seats_max && (
                                  <span>
                                    {table.seats_min}-{table.seats_max}
                                  </span>
                                )}
                                {restrictionReason === "conflict" && (
                                  <span className={styles.restrictionIcon}>
                                    🚫
                                  </span>
                                )}
                                {restrictionReason === "capacity" && (
                                  <span className={styles.restrictionIcon}>
                                    ⚠️
                                  </span>
                                )}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </>
                  ) : (
                    <div className={styles.noTables}>
                      <p>❌ Нет доступных столов</p>
                      <button
                        onClick={handleRefreshTables}
                        className={styles.secondaryButton}
                        disabled={isUpdating}
                      >
                        🔄 Обновить
                      </button>
                    </div>
                  )}

                  <button
                    onClick={() => setShowTableSelection(false)}
                    className={styles.backButton}
                    disabled={isUpdating}
                  >
                    ← Назад
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Изменение статуса */}
          {canManage && availableStatusActions.length > 0 && (
            <div className={styles.section}>
              <h4>Изменить статус</h4>
              <div className={styles.statusGrid}>
                {availableStatusActions.map((action) => (
                  <button
                    key={action.key}
                    onClick={() => handleStatusUpdate(action.key)}
                    disabled={isUpdating}
                    className={styles.statusButton}
                    style={{
                      color: action.color,
                      backgroundColor: action.bgColor,
                      border: `1px solid ${action.color}`,
                    }}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Контактная информация */}
          <div className={styles.section}>
            <div className={styles.contactInfo}>
              <div className={styles.contactLine}>
                <span className={styles.contactLabel}>Телефон:</span>
                <div className={styles.phoneGroup}>
                  <a
                    href={`tel:${booking.phone}`}
                    className={styles.phoneNumber}
                    title="Позвонить"
                  >
                    {booking.phone}
                  </a>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(booking.phone || "");
                    }}
                    className={styles.copyButton}
                    title="Скопировать номер"
                  >
                    📋
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Пожелания */}
          {booking.wishes && (
            <div className={styles.section}>
              <div className={styles.wishes}>
                <span className={styles.wishesIcon}>💬</span>
                {booking.wishes}
              </div>
            </div>
          )}

          {/* Удаление */}
          {canManage && (
            <div className={styles.section}>
              <button
                onClick={handleDelete}
                disabled={isUpdating}
                className={styles.dangerButton}
              >
                {isUpdating ? "Удаление..." : "Удалить бронь"}
              </button>
            </div>
          )}

          {/* Индикатор загрузки */}
          {isUpdating && (
            <div className={styles.loadingOverlay}>
              <div className={styles.spinner}></div>
              <span>Обновление...</span>
            </div>
          )}
        </div>
      )}
    </article>
  );
});

export default BookingCard;
