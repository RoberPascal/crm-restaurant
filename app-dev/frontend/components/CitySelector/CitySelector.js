"use client";

import { useState } from "react";
import styles from "./CitySelector.module.scss";

const cities = ["Москва", "Санкт-Петербург", "Казань"];

export const CitySelector = ({ onSelect }) => {
  const [selected, setSelected] = useState(cities[0]);

  return (
    <select
      className={styles.select}
      value={selected}
      onChange={(e) => {
        setSelected(e.target.value);
        onSelect(e.target.value);
      }}
    >
      {cities.map((city) => (
        <option key={city} value={city}>
          {city}
        </option>
      ))}
    </select>
  );
};
