"use client";

import React from "react";
import { motion } from "framer-motion";
import Image from "next/image";
import styles from "./StaticMap.module.scss";

// Location icon (SVG)
const LocationIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 20 20"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M17.5 8.33333C17.5 14.1667 10 19.1667 10 19.1667C10 19.1667 2.5 14.1667 2.5 8.33333C2.5 6.34421 3.29018 4.43655 4.6967 3.03003C6.10322 1.62351 8.01088 0.833328 10 0.833328C11.9891 0.833328 13.8968 1.62351 15.3033 3.03003C16.7098 4.43655 17.5 6.34421 17.5 8.33333Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M10 10.8333C11.3807 10.8333 12.5 9.71404 12.5 8.33333C12.5 6.95262 11.3807 5.83333 10 5.83333C8.61929 5.83333 7.5 6.95262 7.5 8.33333C7.5 9.71404 8.61929 10.8333 10 10.8333Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

// Metro icon (SVG)
const MetroIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 16 16"
    fill="none"
    aria-hidden="true"
  >
    <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
    <path
      d="M5 8L7 10L11 6"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const StaticMap = React.memo(
  ({ location, restaurant = {}, sectionVariants }) => {
    const lat = Number(location?.lat) || 55.7558;
    const lng = Number(location?.lng) || 37.6173;
    const zoom = 15;

    // Используем OpenStreetMap статичную карту через API StaticMap
    const geoapifyKey = process.env.NEXT_PUBLIC_GEOAPIFY_API_KEY || "";
    const staticMapUrl = `https://maps.geoapify.com/v1/staticmap?style=osm-carto&width=450&height=450&center=lonlat:${lng},${lat}&zoom=${zoom}&marker=lonlat:${lng},${lat};type:material;color:%23ff3421;size:large&apiKey=${geoapifyKey}`;

    const safeName = restaurant?.name || "Бар";
    const safeAddress =
      restaurant?.address || location?.address || "Адрес уточняется";
    const safeMetro = restaurant?.metro || "Метро не указано";

    const handleMapClick = () => {
      // Открываем карту в Telegram если приложение запущено в нем
      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.openLink(
          `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}&zoom=${zoom}`,
        );
      } else {
        // Иначе открываем в новой вкладке
        window.open(
          `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}&zoom=${zoom}`,
          "_blank",
        );
      }
    };

    return (
      <motion.section
        id="map"
        className={styles.section}
        variants={sectionVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-100px" }}
        role="region"
        aria-label="Карта расположения"
      >
        <div className={styles.header}>
          <h2 className={styles.title}>Карта</h2>
        </div>

        <div className={styles.mapWrapper}>
          <div
            className={styles.mapContainer}
            role="img"
            aria-label={`${safeName}, ${safeAddress}`}
          >
            <div className={styles.staticMap} onClick={handleMapClick}>
              <Image
                src={staticMapUrl}
                alt={`Карта расположения: ${safeAddress}`}
                fill
                sizes="(max-width: 450px) 100vw, 450px"
                priority
              />
              <div className={styles.mapOverlay}>
                <span className={styles.tapHint}>
                  Нажмите, чтобы открыть карту
                </span>
              </div>
            </div>

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
          </div>
        </div>
      </motion.section>
    );
  },
);

StaticMap.displayName = "StaticMap";
