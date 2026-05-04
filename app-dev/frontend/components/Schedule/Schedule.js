"use client";

import { useState } from "react";
import styles from "./Schedule.module.scss";

export const Schedule = ({ schedule }) => {
  const [expanded, setExpanded] = useState(false);
  const today = new Date()
    .toLocaleDateString("ru-RU", { weekday: "long" })
    .toLowerCase();
  const todayHours = schedule[today] || "Закрыто";

  return (
    <div className={styles.schedule}>
      <p>Сегодня Открыто до {todayHours.split(" - ")[1]}</p>
      <button
        onClick={() => setExpanded(!expanded)}
        className={styles.toggleButton}
      >
        {expanded ? "Свернуть" : "Развернуть график"}
      </button>
      {expanded && (
        <ul>
          {Object.entries(schedule).map(([day, hours]) => (
            <li key={day}>
              {day.charAt(0).toUpperCase() + day.slice(1)}: {hours}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
