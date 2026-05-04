// components/AdminPanel/AdminPanel.jsx
"use client";

import { useState, useEffect } from "react";
import styles from "./AdminPanel.module.scss";
import { api } from "@/utils/api";
import { useDashboard } from "@/context/DashboardContext";

// Иконки
const Icons = {
  Save: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M17 21v-8H7v8"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M7 3v5h8"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Close: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Download: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polyline
        points="7,10 12,15 17,10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <line
        x1="12"
        y1="15"
        x2="12"
        y2="3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
};

const Spinner = () => (
  <svg className={styles.spinner} width="16" height="16" viewBox="0 0 24 24">
    <circle
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="2"
      fill="none"
      strokeDasharray="15"
    />
  </svg>
);

export default function AdminPanel() {
  const { restaurants: ctxRestaurants } = useDashboard();

  const [restaurants, setRestaurants] = useState([]);
  const [selectedRestaurantId, setSelectedRestaurantId] = useState(null);
  const [lastBookingTimeInput, setLastBookingTimeInput] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [saving, setSaving] = useState(false);
  const [working, setWorking] = useState(false);

  // Инициализация ресторанов
  useEffect(() => {
    if (ctxRestaurants?.length) {
      setRestaurants(ctxRestaurants);
      setSelectedRestaurantId((prev) => prev ?? ctxRestaurants[0].id);
    } else {
      setRestaurants([]);
      setSelectedRestaurantId(null);
    }
  }, [ctxRestaurants]);

  // Загрузка деталей ресторана
  useEffect(() => {
    const loadRestaurantDetails = async () => {
      if (!selectedRestaurantId) {
        setLastBookingTimeInput("");
        return;
      }

      try {
        const data = await api.get(
          `/api/v1/admin/restaurants/${selectedRestaurantId}`,
        );
        setLastBookingTimeInput(data.last_booking_time || "");
      } catch (error) {
        console.error("Failed to load restaurant details:", error);
      }
    };

    loadRestaurantDetails();
  }, [selectedRestaurantId]);

  // Обработчики действий
  const handleSaveLastBookingTime = async () => {
    if (!selectedRestaurantId) return;

    if (lastBookingTimeInput && !/^\d{2}:\d{2}$/.test(lastBookingTimeInput)) {
      alert("Введите время в формате ЧЧ:ММ или оставьте пустым");
      return;
    }

    try {
      setSaving(true);
      await api.patch(
        `/api/v1/admin/restaurants/${selectedRestaurantId}/settings/last-booking-time`,
        { last_booking_time: lastBookingTimeInput || null },
      );

      const data = await api.get(
        `/api/v1/admin/restaurants/${selectedRestaurantId}`,
      );
      setLastBookingTimeInput(data.last_booking_time || "");
      alert("Сохранено");
    } catch (error) {
      alert(`Ошибка сохранения: ${error.message || "Неизвестная ошибка"}`);
    } finally {
      setSaving(false);
    }
  };

  const handleCloseDay = async () => {
    if (!selectedRestaurantId || !targetDate) {
      alert("Выберите ресторан и дату");
      return;
    }

    if (!window.confirm(`Закрыть все слоты на ${targetDate}?`)) return;

    try {
      setWorking(true);
      await api.post(
        `/api/v1/admin/restaurants/${selectedRestaurantId}/slots/close-day`,
        { date: targetDate },
      );
      alert("День закрыт для бронирований");
      setTargetDate("");
    } catch (error) {
      alert(`Ошибка: ${error.message || "Неизвестная ошибка"}`);
    } finally {
      setWorking(false);
    }
  };

  const handleExportCsv = async () => {
    if (!selectedRestaurantId || !rangeStart || !rangeEnd) {
      alert("Выберите ресторан и диапазон для экспорта");
      return;
    }

    try {
      const dates = [];
      let currentDate = new Date(rangeStart + "T00:00:00");
      const endDate = new Date(rangeEnd + "T00:00:00");

      while (currentDate <= endDate) {
        dates.push(currentDate.toISOString().slice(0, 10));
        currentDate.setDate(currentDate.getDate() + 1);
      }

      const rows = [
        [
          "id",
          "date",
          "time",
          "status",
          "name",
          "phone",
          "capacity",
          "table_id",
        ],
      ];

      // ОПТИМИЗАЦИЯ: параллельные запросы батчами по 5 вместо последовательных
      const BATCH_SIZE = 5;
      for (let i = 0; i < dates.length; i += BATCH_SIZE) {
        const batch = dates.slice(i, i + BATCH_SIZE);
        const results = await Promise.all(
          batch.map((day) =>
            api
              .get(
                `/api/v1/admin/bookings?restaurant_id=${selectedRestaurantId}&date=${day}`,
              )
              .catch(() => []),
          ),
        );

        results.forEach((data) => {
          (data || []).forEach((booking) => {
            rows.push([
              booking.id,
              booking.date,
              booking.time,
              booking.status,
              booking.name || "",
              booking.phone || "",
              booking.capacity_category || "",
              booking.table?.number || booking.table_id || "",
            ]);
          });
        });
      }

      const csvContent = rows
        .map((row) =>
          row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","),
        )
        .join("\n");

      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = url;
      link.download = `bookings_${selectedRestaurantId}_${rangeStart}_${rangeEnd}.csv`;
      link.click();

      URL.revokeObjectURL(url);
    } catch (error) {
      alert("Ошибка экспорта CSV");
    }
  };

  const handleRestaurantChange = (e) => {
    const value = parseInt(e.target.value);
    setSelectedRestaurantId(value || null);
  };

  return (
    <div className={styles.adminPanel}>
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Настройки бронирований</h2>

        <div className={styles.row}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Ресторан</label>
            <select
              className={styles.formSelect}
              value={selectedRestaurantId || ""}
              onChange={handleRestaurantChange}
            >
              {restaurants.map((restaurant) => (
                <option key={restaurant.id} value={restaurant.id}>
                  {restaurant.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className={styles.row}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>
              Последнее время бронирования (ЧЧ:ММ)
            </label>
            <input
              type="text"
              className={`${styles.formInput} ${styles.timeInput}`}
              placeholder="например, 22:00"
              value={lastBookingTimeInput}
              onChange={(e) => setLastBookingTimeInput(e.target.value)}
              maxLength={5}
            />
            <div className={styles.infoText}>
              Глобальная настройка для всех дней. Оставьте пустым, чтобы убрать
              ограничение.
            </div>
          </div>
          <button
            className={styles.formButton}
            onClick={handleSaveLastBookingTime}
            disabled={saving || !selectedRestaurantId}
          >
            {saving ? <Spinner /> : <Icons.Save />}
            {saving ? "Сохранение..." : "Сохранить"}
          </button>
        </div>
      </div>

      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Закрыть бронирование на день</h2>
        <div className={styles.row}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>Дата закрытия</label>
            <input
              type="date"
              className={styles.formInput}
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
            />
            <div className={styles.warningText}>
              Все слоты на выбранную дату будут закрыты для бронирования.
            </div>
          </div>
          <button
            className={`${styles.formButton} ${styles.deleteButton}`}
            onClick={handleCloseDay}
            disabled={working || !selectedRestaurantId || !targetDate}
          >
            {working ? <Spinner /> : <Icons.Close />}
            {working ? "Выполняется..." : "Закрыть день"}
          </button>
        </div>
      </div>

      {/* CSV export hidden - not in current requirements */}
    </div>
  );
}
