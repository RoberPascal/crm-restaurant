"use client";
import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { format, parseISO, isSameDay, isAfter } from "date-fns";
import { toZonedTime, fromZonedTime } from "date-fns-tz";
import { ru } from "date-fns/locale";
import {
  Calendar,
  Clock,
  Users,
  FileText,
  Phone,
  CheckCircle2,
  Utensils,
} from "lucide-react";
import { Header } from "@/components/Header/Header";
import { api } from "@/utils/api";
import styles from "./Bookings.module.scss";

const MOSCOW_TZ = "Europe/Moscow";

// Обновленные иконки с правильными размерами
const CalendarIcon = () => <Calendar size={20} strokeWidth={1.6} />;
const ClockIcon = () => <Clock size={20} strokeWidth={1.6} />;
const UserIcon = () => <Users size={20} strokeWidth={1.8} />;
const TableIcon = () => <Utensils size={20} strokeWidth={1.6} />;
const NoteIcon = () => <FileText size={20} strokeWidth={1.6} />;
const PhoneIcon = () => <Phone size={20} strokeWidth={1.6} />;
const StatusIcon = () => <CheckCircle2 size={18} strokeWidth={1.6} />;

const STATUS_CONFIG = {
  pending: {
    label: "Подтверждено",
    tone: "#4ade80",
    bg: "rgba(74, 222, 128, 0.08)",
    border: "rgba(74, 222, 128, 0.3)",
  },
  confirmed: {
    label: "Подтверждено",
    tone: "#4ade80",
    bg: "rgba(74, 222, 128, 0.08)",
    border: "rgba(74, 222, 128, 0.3)",
  },
  assigned: {
    label: "Назначен стол",
    tone: "#60a5fa",
    bg: "rgba(96, 165, 250, 0.08)",
    border: "rgba(96, 165, 250, 0.3)",
  },
  pending_review: {
    label: "Подтверждено",
    tone: "#4ade80",
    bg: "rgba(74, 222, 128, 0.08)",
    border: "rgba(74, 222, 128, 0.3)",
  },
  arrived: {
    label: "Прибыл",
    tone: "#38bdf8",
    bg: "rgba(56, 189, 248, 0.08)",
    border: "rgba(56, 189, 248, 0.3)",
  },
  cancelled: {
    label: "Отменено",
    tone: "#f87171",
    bg: "rgba(248, 113, 113, 0.08)",
    border: "rgba(248, 113, 113, 0.3)",
  },
  no_show: {
    label: "Не пришёл",
    tone: "#f87171",
    bg: "rgba(248, 113, 113, 0.08)",
    border: "rgba(248, 113, 113, 0.3)",
  },
  completed: {
    label: "Завершено",
    tone: "#c084fc",
    bg: "rgba(192, 132, 252, 0.08)",
    border: "rgba(192, 132, 252, 0.3)",
  },
};

const getStatusConfig = (status) => {
  const config = STATUS_CONFIG[status] || {
    label: status,
    tone: "#94a3b8",
    bg: "rgba(148, 163, 184, 0.1)",
    border: "rgba(148, 163, 184, 0.3)",
  };
  return { ...config, icon: StatusIcon };
};

// Получаем текущее время в Москве
const getCurrentMoscowTime = () => {
  return toZonedTime(new Date(), MOSCOW_TZ);
};

// Создаем дату и время брони в московском часовом поясе
const getBookingDateTime = (booking) => {
  try {
    // Backend уже возвращает date/time в московском времени, просто парсим
    const date =
      typeof booking.date === "string" ? parseISO(booking.date) : booking.date;
    const [hours = 0, minutes = 0] = (booking.time || "00:00")
      .split(":")
      .map(Number);

    // Создаем полную дату-время (уже в московском времени)
    const bookingDateTime = new Date(date);
    bookingDateTime.setHours(hours, minutes, 0, 0);

    return bookingDateTime;
  } catch (error) {
    console.error("Error parsing booking date:", error);
    return new Date(); // Возвращаем текущее время в случае ошибки
  }
};

export default function Bookings() {
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [currentMoscowTime, setCurrentMoscowTime] = useState(
    getCurrentMoscowTime(),
  );

  // Обновляем московское время каждую минуту
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentMoscowTime(getCurrentMoscowTime());
    }, 60000); // 1 минута

    return () => clearInterval(timer);
  }, []);

  const fetchBookings = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.get("/api/v1/public/bookings/me");
      setBookings(data || []);
    } catch (err) {
      console.error("Failed to fetch bookings:", err);
      setError(err.message || "Не удалось загрузить бронирования");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBookings();
  }, []);

  const handleDelete = async (bookingId) => {
    if (
      !confirm(
        "Вы уверены, что хотите УДАЛИТЬ это бронирование?\nЭто действие нельзя отменить.",
      )
    ) {
      return;
    }

    try {
      setDeletingId(bookingId);
      await api.delete(`/api/v1/public/bookings/${bookingId}`);
      await fetchBookings();
    } catch (err) {
      console.error("Failed to delete booking:", err);
      alert(err.message || "Не удалось удалить бронирование");
    } finally {
      setDeletingId(null);
    }
  };

  const handleNotifyDelay = async (bookingId) => {
    try {
      await api.post(`/api/v1/public/bookings/${bookingId}/notify-delay`);
      alert("Персонал уведомлен об опоздании");
    } catch (err) {
      console.error("Failed to notify delay:", err);
      alert(err.message || "Не удалось отправить уведомление");
    }
  };

  const formatDate = (dateValue) => {
    try {
      const date =
        typeof dateValue === "string" ? parseISO(dateValue) : dateValue;

      // date уже в московском времени с бэкенда, не конвертируем повторно
      if (isSameDay(date, currentMoscowTime)) {
        return "Сегодня";
      }
      return format(date, "d MMMM", { locale: ru });
    } catch {
      return String(dateValue);
    }
  };

  const formatTime = (timeValue) => {
    if (!timeValue) return "";
    try {
      if (typeof timeValue === "string") {
        const [h = "00", m = "00"] = timeValue.split(":");
        return `${h.padStart(2, "0")}:${m.padStart(2, "0")}`;
      }
      return timeValue;
    } catch {
      return timeValue;
    }
  };

  // ИСПРАВЛЕННАЯ логика отмены - сравниваем в московском времени
  const canCancel = (booking) => {
    // 1. Нельзя отменять завершенные/отмененные брони
    if (["cancelled", "completed", "no_show"].includes(booking.status)) {
      return false;
    }

    // 2. Проверяем, не прошло ли время бронирования (в московском времени)
    try {
      const bookingDateTime = getBookingDateTime(booking);
      return isAfter(bookingDateTime, currentMoscowTime);
    } catch {
      // В случае ошибки разрешаем отмену (безопасный вариант)
      return true;
    }
  };

  const sortedBookings = useMemo(() => {
    return [...bookings].sort((a, b) => {
      try {
        const dateA = getBookingDateTime(a);
        const dateB = getBookingDateTime(b);
        return dateB.getTime() - dateA.getTime(); // Сначала новые
      } catch {
        return 0;
      }
    });
  }, [bookings]);

  if (loading) {
    return (
      <div className={styles.container}>
        <Header showBackButton />
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <p>Загрузка бронирований...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <Header showBackButton />
        <div className={styles.error}>
          <p>{error}</p>
          <button onClick={fetchBookings} className={styles.retryButton}>
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <Header showBackButton />
      <motion.main
        className={styles.main}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <h1>Мои бронирования</h1>
        {sortedBookings.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>—</div>
            <p>У вас пока нет активных бронирований</p>
            <p className={styles.emptySubtext}>
              Забронируйте стол и вернитесь позже
            </p>
          </div>
        ) : (
          <div className={styles.list}>
            <AnimatePresence>
              {sortedBookings.map((booking) => {
                const status = getStatusConfig(booking.status);
                const guestsTotal = booking.adults + (booking.children || 0);
                const allowCancel = canCancel(booking);
                const StatusBadgeIcon = status.icon;

                return (
                  <motion.article
                    key={booking.id}
                    className={styles.bookingCard}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <div className={styles.cardTop}>
                      <div className={styles.timeBlock}>
                        <span className={styles.timePrimary}>
                          {formatTime(booking.time)}
                        </span>
                        {booking.end_time && (
                          <span className={styles.timeSecondary}>
                            — {formatTime(booking.end_time)}
                          </span>
                        )}
                        <span className={styles.dateLabel}>
                          {formatDate(booking.date)}
                        </span>
                      </div>
                      <span
                        className={styles.statusBadge}
                        style={{
                          color: status.tone,
                          backgroundColor: status.bg,
                          borderColor: status.border,
                        }}
                      >
                        <StatusBadgeIcon />
                        {status.label}
                      </span>
                    </div>

                    <div className={styles.cardTitle}>
                      <h3>{booking.restaurant_name || "Бар"}</h3>
                      {booking.restaurant_slug && (
                        <span>@{booking.restaurant_slug}</span>
                      )}
                    </div>

                    <div className={styles.infoGrid}>
                      <div className={styles.infoRow}>
                        <div className={styles.infoIcon}>
                          <CalendarIcon />
                        </div>
                        <div className={styles.infoContent}>
                          <span>Дата</span>
                          <strong>{formatDate(booking.date)}</strong>
                        </div>
                      </div>

                      <div className={styles.infoRow}>
                        <div className={styles.infoIcon}>
                          <ClockIcon />
                        </div>
                        <div className={styles.infoContent}>
                          <span>Время</span>
                          <strong>
                            {formatTime(booking.time)}
                            {booking.end_time && (
                              <em> — {formatTime(booking.end_time)}</em>
                            )}
                          </strong>
                        </div>
                      </div>

                      <div className={styles.infoRow}>
                        <div className={styles.infoIcon}>
                          <UserIcon />
                        </div>
                        <div className={styles.infoContent}>
                          <span>Гостей</span>
                          <strong>
                            {guestsTotal}
                            {booking.children > 0 && (
                              <em>
                                {" "}
                                ({booking.adults} взросл
                                {booking.adults === 1 ? "ый" : "ых"},{" "}
                                {booking.children} дет
                                {booking.children === 1 ? "ь" : "ей"})
                              </em>
                            )}
                          </strong>
                        </div>
                      </div>

                      {booking.table_number && (
                        <div className={styles.infoRow}>
                          <div className={styles.infoIcon}>
                            <TableIcon />
                          </div>
                          <div className={styles.infoContent}>
                            <span>Стол</span>
                            <strong>#{booking.table_number}</strong>
                          </div>
                        </div>
                      )}

                      <div className={styles.infoRow}>
                        <div className={styles.infoIcon}>
                          <PhoneIcon />
                        </div>
                        <div className={styles.infoContent}>
                          <span>Телефон</span>
                          <a href={`tel:${booking.phone}`}>{booking.phone}</a>
                        </div>
                      </div>

                      {booking.wishes && (
                        <div className={styles.infoRow}>
                          <div className={styles.infoIcon}>
                            <NoteIcon />
                          </div>
                          <div className={styles.infoContent}>
                            <span>Пожелания</span>
                            <p>{booking.wishes}</p>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className={styles.cardActions}>
                      {allowCancel && (
                        <button
                          onClick={() => handleNotifyDelay(booking.id)}
                          className={styles.notifyButton}
                        >
                          Сообщить об опоздании
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(booking.id)}
                        disabled={deletingId === booking.id}
                        className={styles.deleteButton}
                      >
                        {deletingId === booking.id ? (
                          <>
                            <div className={styles.spinnerSmall} />
                            Удаление...
                          </>
                        ) : (
                          "Удалить"
                        )}
                      </button>
                    </div>
                  </motion.article>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </motion.main>
    </div>
  );
}
