"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { YMaps, Map, Placemark } from "@pbe/react-yandex-maps";
import styles from "./YandexMap.module.scss";

// Location icon - минималистичный
const LocationIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
    <path
      d="M10 1C6.1 1 3 4.1 3 8C3 13.2 10 19 10 19C10 19 17 13.2 17 8C17 4.1 13.9 1 10 1Z"
      stroke="currentColor"
      strokeWidth="1.5"
    />
    <circle cx="10" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

// Metro icon - стильная буква М
const MetroIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
    <path
      d="M4 15L7 5L10 11L13 5L16 15"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M3 15H17"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);

/**
 * YandexMap: Map with placemark and address card inside.
 */
export const YandexMap = React.memo(
  ({ location, restaurant = {}, sectionVariants }) => {
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
      setIsLoading(true);
      setError(null);

      const lat = Number(location?.lat);
      const lng = Number(location?.lng);

      if (location && (isNaN(lat) || isNaN(lng))) {
        setError("Некорректные координаты — используется центр Москвы");
        setIsLoading(false);
        return;
      }

      setTimeout(() => setIsLoading(false), 800);
    }, [location]);

    const defaultState = {
      center: [
        Number(location?.lat) || 55.7558,
        Number(location?.lng) || 37.6173,
      ],
      zoom: 15,
    };

    const placemarkOptions = {
      preset: "islands#dotIcon",
      iconColor: "#28a745",
    };

    const safeName = restaurant?.name || "Бар";
    const safeAddress =
      restaurant?.address || location?.address || "Адрес уточняется";
    const safeMetro = restaurant?.metro || "Метро не указано";

    const geometry = [
      Number(location?.lat) || 55.7558,
      Number(location?.lng) || 37.6173,
    ];

    return (
      <motion.section
        id="map"
        className={styles.section}
        variants={sectionVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-100px" }}
      >
        <div className={styles.header}>
          <h2 className={styles.title}>Карта</h2>
        </div>

        <div className={styles.mapWrapper}>
          <div className={styles.mapContainer}>
            {isLoading ? (
              <div className={styles.loader}>
                <div className={styles.spinner}></div>
                <p>Загрузка карты...</p>
              </div>
            ) : error ? (
              <div className={styles.error}>
                <LocationIcon />
                <p>{error}</p>
              </div>
            ) : (
              <>
                <YMaps
                  query={{
                    apikey: process.env.NEXT_PUBLIC_YANDEX_MAPS_API_KEY,
                  }}
                >
                  <Map
                    defaultState={defaultState}
                    className={styles.map}
                    options={{ suppressMapOpenBlock: true }}
                  >
                    <Placemark
                      geometry={geometry}
                      properties={{ hintContent: safeAddress }}
                      options={placemarkOptions}
                    />
                  </Map>
                </YMaps>

                <motion.div
                  className={styles.addressCard}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3, duration: 0.4 }}
                >
                  <div className={styles.addressContent}>
                    <div className={styles.addressRow}>
                      <div className={styles.iconWrapper}>
                        <LocationIcon />
                      </div>
                      <div className={styles.addressInfo}>
                        <div className={styles.addressLabel}>Адрес</div>
                        <div className={styles.addressText}>{safeAddress}</div>
                      </div>
                    </div>

                    <div className={styles.addressRow}>
                      <div className={styles.iconWrapper}>
                        <MetroIcon />
                      </div>
                      <div className={styles.addressInfo}>
                        <div className={styles.addressLabel}>Метро</div>
                        <div className={styles.addressText}>{safeMetro}</div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              </>
            )}
          </div>
        </div>
      </motion.section>
    );
  }
);

YandexMap.displayName = "YandexMap";
