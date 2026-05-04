// web-app/components/BookingSection/BookingSection.jsx
"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import BookingTimeSelector from "../BookingTimeSelector/BookingTimeSelector";
import { api } from "@/utils/api";
import styles from "./BookingSection.module.scss";

export function BookingSection({ onOpenBooking, restaurant, sectionVariants }) {
  const [selectedCapacity, setSelectedCapacity] = useState(null);
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [availableTimes, setAvailableTimes] = useState([]);

  const capacities = [
    { id: "small", label: "2-3 человека", icon: "👫" },
    { id: "medium", label: "4-6 человек", icon: "👨‍👩‍👧‍👦" },
    { id: "large", label: "8+ человек", icon: "👨‍👩‍👧‍👦👨‍👩‍👧‍👦" },
  ];

  const handleCapacitySelect = async (capacity) => {
    setSelectedCapacity(capacity);

    // Загружаем доступные слоты
    try {
      const data = await api.get(
        `/api/v1/public/slots/availability?restaurant_id=${restaurant.id}&booking_date=${
          selectedDate.toISOString().split("T")[0]
        }&capacity=${capacity.id}`,
      );
      if (Array.isArray(data)) {
        setAvailableTimes(data.filter((slot) => slot.is_available));
      }
    } catch (error) {
      // error handled by api utility
    }
  };

  const handleTimeSelect = (time, date) => {
    onOpenBooking({
      capacity: selectedCapacity,
      time,
      date: new Date(date).toISOString().split("T")[0],
    });
  };

  return (
    <motion.section
      className={styles.section}
      variants={sectionVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-100px" }}
    >
      <div className={styles.container}>
        <motion.div
          className={styles.content}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          viewport={{ once: true }}
        >
          <h2 className={styles.title}>
            Забронируйте столик в {restaurant.name}
          </h2>

          <p className={styles.subtitle}>
            Выберите количество гостей и удобное время
          </p>

          {!selectedCapacity ? (
            <div className={styles.capacityGrid}>
              {capacities.map((cap) => (
                <motion.button
                  key={cap.id}
                  className={styles.capacityCard}
                  onClick={() => handleCapacitySelect(cap)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  transition={{ type: "spring", stiffness: 400 }}
                >
                  <div className={styles.capacityIcon}>{cap.icon}</div>
                  <div className={styles.capacityLabel}>{cap.label}</div>
                </motion.button>
              ))}
            </div>
          ) : (
            <BookingTimeSelector
              restaurant={restaurant}
              capacity={selectedCapacity}
              date={selectedDate}
              onTimeSelect={handleTimeSelect}
              onBack={() => setSelectedCapacity(null)}
            />
          )}
        </motion.div>
      </div>
    </motion.section>
  );
}
