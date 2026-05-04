// web-app/components/BookingTimeSelector/BookingTimeSelector.jsx
"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { api } from "@/utils/api";
import styles from "./BookingTimeSelector.module.scss";

export default function BookingTimeSelector({
  restaurant,
  capacity,
  date,
  onTimeSelect,
  onBack,
}) {
  const [loading, setLoading] = useState(true);
  const [availableTimes, setAvailableTimes] = useState([]);
  const [selectedTime, setSelectedTime] = useState(null);
  const [error, setError] = useState(null);

  const loadAvailableTimes = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const dateStr = new Date(date).toISOString().split("T")[0];
      const data = await api.get(
        `/api/v1/public/slots/availability?restaurant_slug=${restaurant.slug}&booking_date=${dateStr}&capacity=${capacity.id}`,
      );
      if (Array.isArray(data)) {
        const available = data.filter((slot) => slot.is_available);
        setAvailableTimes(available);

        if (available.length === 0) {
          setError("На выбранное время мест нет");
        }
      } else {
        setError("Не удалось загрузить доступное время");
      }
    } catch (err) {
      setError("Ошибка сети");
    } finally {
      setLoading(false);
    }
  }, [restaurant.slug, date, capacity.id]);

  useEffect(() => {
    loadAvailableTimes();
  }, [loadAvailableTimes]);

  if (loading) {
    return (
      <div className={styles.loading}>
        <div className={styles.spinner}></div>
        <p>Загружаем доступное время...</p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>
          ← Назад
        </button>
        <h2 className={styles.title}>
          {capacity.label} •{" "}
          {new Date(date).toLocaleDateString("ru-RU", {
            weekday: "short",
            day: "numeric",
            month: "short",
          })}
        </h2>
      </div>

      {error ? (
        <div className={styles.error}>
          <div className={styles.errorIcon}>😔</div>
          <p>{error}</p>
          <button className={styles.retryBtn} onClick={loadAvailableTimes}>
            Попробовать снова
          </button>
        </div>
      ) : availableTimes.length === 0 ? (
        <div className={styles.noSlots}>
          <div className={styles.noSlotsIcon}>⏰</div>
          <h3>На это время мест нет</h3>
          <p>Попробуйте выбрать другое время или количество гостей</p>
          <button className={styles.changeBtn} onClick={onBack}>
            Изменить количество гостей
          </button>
        </div>
      ) : (
        <div className={styles.timeGrid}>
          {availableTimes.slice(0, 16).map(
            (
              slot, // Максимум 16 слотов
            ) => (
              <motion.button
                key={slot.time}
                className={`${styles.timeCard} ${
                  selectedTime === slot.time ? styles.selected : ""
                }`}
                onClick={() => {
                  setSelectedTime(slot.time);
                  onTimeSelect(slot.time, date);
                }}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                transition={{ type: "spring", stiffness: 400, damping: 17 }}
              >
                <div className={styles.time}>{slot.time}</div>
                {slot.available_capacity && (
                  <div className={styles.capacity}>
                    {slot.available_capacity} мест
                  </div>
                )}
              </motion.button>
            ),
          )}

          {availableTimes.length > 16 && (
            <div className={styles.moreIndicator}>
              Еще {availableTimes.length - 16} временных слотов
            </div>
          )}
        </div>
      )}
    </div>
  );
}
