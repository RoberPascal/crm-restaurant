"use client";

import { useState, useEffect, useRef } from "react";
import {
  getMoscowStartOfDay,
  addMoscowDays,
  isSameMoscowDay,
  formatDateForAPI,
  formatDisplayDate,
} from "@/utils/date";
import Portal from "../Portal/Portal";
import styles from "./DateSelector.module.scss";

export default function DateSelector({
  selectedDate,
  onDateChange,
  isLoading,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentMonthStart, setCurrentMonthStart] = useState(() =>
    getMoscowStartOfDay(selectedDate)
  );
  const modalRef = useRef(null);

  const today = getMoscowStartOfDay();
  // Убираем ограничения: можно выбрать любую дату от года назад до +30 дней
  const minDate = addMoscowDays(today, -365); // Год назад
  const maxDate = addMoscowDays(today, 30);

  // Закрытие модального окна при клике вне его
  useEffect(() => {
    const handleClickOutside = (event) => {
      const modal = modalRef.current;
      const dateButton = document.querySelector(`.${styles.date}`);

      if (
        modal &&
        !modal.contains(event.target) &&
        dateButton &&
        !dateButton.contains(event.target)
      ) {
        setIsOpen(false);
      }
    };

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleEscape);

      if (window.innerWidth <= 768) {
        document.body.style.overflow = "hidden";
      }
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  useEffect(() => {
    const ymd = formatDateForAPI(selectedDate);
    const [y, m] = ymd.split("-").map(Number);
    setCurrentMonthStart(new Date(Date.UTC(y, m - 1, 1, 3)));
  }, [selectedDate]);

  const handlePrev = () => {
    const prev = addMoscowDays(selectedDate, -1);
    if (prev >= minDate) onDateChange(prev);
  };

  const handleNext = () => {
    const next = addMoscowDays(selectedDate, 1);
    if (next <= maxDate) onDateChange(next);
  };

  const handleDateSelect = (date) => {
    onDateChange(date);
    // Закрываем календарь после выбора на мобильных устройствах
    if (window.innerWidth <= 768) {
      setIsOpen(false);
    }
  };

  const renderDays = () => {
    const days = [];
    const y = currentMonthStart.getUTCFullYear();
    const m = currentMonthStart.getUTCMonth();
    const firstDayOfMonth = new Date(Date.UTC(y, m, 1, 3));
    const firstDayIndex = (firstDayOfMonth.getUTCDay() + 6) % 7;

    for (let i = 0; i < firstDayIndex; i++) {
      days.push(<div key={`empty-${i}`} className={styles.empty} />);
    }

    const monthLength = new Date(Date.UTC(y, m + 1, 0, 3)).getUTCDate();

    for (let day = 1; day <= monthLength; day++) {
      const dateInMSK = new Date(Date.UTC(y, m, day, 3));
      const isSel = isSameMoscowDay(dateInMSK, selectedDate);
      const isToday = isSameMoscowDay(dateInMSK, today);
      const disabled = dateInMSK < minDate || dateInMSK > maxDate;

      days.push(
        <button
          key={day}
          className={`${styles.day} ${isSel ? styles.selected : ""} ${
            isToday ? styles.today : ""
          } ${disabled ? styles.disabled : ""}`}
          onClick={() => !disabled && handleDateSelect(dateInMSK)}
          disabled={disabled}
        >
          {day}
        </button>
      );
    }

    return days;
  };

  const monthLabel = currentMonthStart.toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });

  // Для мобильных устройств рендерим оверлей
  const ModalContent = () => (
    <div className={styles.modal} ref={modalRef}>
      <div className={styles.modalHeader}>
        <button
          onClick={() =>
            setCurrentMonthStart(addMoscowDays(currentMonthStart, -30))
          }
          type="button"
          className={styles.navButton}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M15 18L9 12L15 6" stroke="currentColor" strokeWidth="2" />
          </svg>
        </button>
        <span className={styles.monthLabel}>{monthLabel}</span>
        <div className={styles.headerRight}>
          <button
            onClick={() =>
              setCurrentMonthStart(addMoscowDays(currentMonthStart, 32))
            }
            type="button"
            className={styles.navButton}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path d="M9 18L15 12L9 6" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>
        </div>
      </div>
      <div className={styles.weekdays}>
        {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
      <div className={styles.days}>{renderDays()}</div>
    </div>
  );

  // Убрали кнопку "Сегодня" — больше не нужна

  return (
    <div className={styles.dateSelector}>
      <div className={styles.block}>
        <button
          onClick={handlePrev}
          disabled={selectedDate <= minDate}
          className={styles.nav}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M15 18L9 12L15 6" stroke="currentColor" strokeWidth="2" />
          </svg>
        </button>
        <button
          className={styles.date}
          onClick={() => setIsOpen(!isOpen)}
          type="button"
          disabled={isLoading}
        >
          {isLoading ? (
            <div className={styles.loadingSpinner}>
              <span>Загрузка...</span>
            </div>
          ) : (
            formatDisplayDate(selectedDate)
          )}
        </button>
        <button
          onClick={handleNext}
          className={styles.nav}
          disabled={selectedDate >= maxDate}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M9 18L15 12L9 6" stroke="currentColor" strokeWidth="2" />
          </svg>
        </button>
        {null}
      </div>

      {isOpen && (
        <Portal>
          <>
            {/* Оверлей для мобильных */}
            {typeof window !== "undefined" && window.innerWidth <= 768 && (
              <div
                className={styles.overlay}
                onClick={() => setIsOpen(false)}
              />
            )}
            <ModalContent />
          </>
        </Portal>
      )}
    </div>
  );
}
