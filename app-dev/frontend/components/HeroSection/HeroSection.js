"use client";

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import Image from "next/image";
import styles from "./HeroSection.module.scss";

// Memoized clock icon with proper accessibility
const ClockIcon = React.memo(() => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
    focusable="false"
  >
    <path
      d="M12 7V12H17M12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12C21 16.9706 16.9706 21 12 21Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
));
ClockIcon.displayName = "ClockIcon";

// Memoized money icon with proper accessibility
const MoneyIcon = React.memo(() => (
  <svg
    width="24"
    height="24"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
    focusable="false"
  >
    <path
      d="M11.5 15C10.6716 15 10 14.3284 10 13.5C10 12.6716 10.6716 12 11.5 12M3 15.8002V8.2002C3 7.08009 3 6.51962 3.21799 6.0918C3.40973 5.71547 3.71547 5.40973 4.0918 5.21799C4.51962 5 5.08009 5 6.2002 5H17.8002C18.9203 5 19.4796 5 19.9074 5.21799C20.2837 5.40973 20.5905 5.71547 20.7822 6.0918C21 6.5192 21 7.07899 21 8.19691V15.8036C21 16.9215 21 17.4805 20.7822 17.9079C20.5905 18.2842 20.2837 18.5905 19.9074 18.7822C19.48 19 18.921 19 17.8031 19H6.19691C5.07899 19 4.5192 19 4.0918 18.7822C3.71547 18.5905 3.40973 18.2842 3.21799 17.9079C3 17.4801 3 16.9203 3 15.8002ZM17 13.5C17 14.3284 16.3284 15 15.5 15C14.6716 15 14 14.3284 14 13.5C14 12.6716 14.6716 12 15.5 12C16.3284 12 17 12.6716 17 13.5Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
));
MoneyIcon.displayName = "MoneyIcon";

const HeroSection = React.memo(
  ({
    restaurant = {},
    heroRef,
    isOpen = false,
    imageUrl = "/default-hero.jpg",
    blurDataURL = null,
  }) => {
    // Safe handling of props with proper formatting
    const safeName = restaurant.name || "Бар";
    const safeAddress = restaurant.address || "Адрес уточняется";

    const safeAvgCheck = useMemo(() => {
      if (!restaurant.avgCheck) return "Уточняется";

      const checkValue = Number(restaurant.avgCheck);
      if (isNaN(checkValue)) return "Уточняется";

      return `${checkValue.toLocaleString("ru-RU")} ₽`;
    }, [restaurant.avgCheck]);

    const fullStatus = useMemo(() => {
      return isOpen ? "ОТКРЫТО" : "ЗАКРЫТО";
    }, [isOpen]);

    const statusAriaLabel = useMemo(() => {
      return isOpen ? "Бар открыт" : "Бар закрыт";
    }, [isOpen]);

    return (
      <section
        className={styles.heroWrapper}
        ref={heroRef}
        role="banner"
        aria-label={`${safeName} - ${safeAddress}`}
      >
        <div className={styles.imageContainer}>
          <Image
            src={imageUrl}
            alt={`Интерьер бара ${safeName}`}
            className={styles.heroImage}
            fill
            sizes="100vw"
            quality={85}
            priority // Hero image should be prioritized
            placeholder={blurDataURL ? "blur" : "empty"}
            blurDataURL={blurDataURL}
          />
          <div className={styles.imageOverlay} />
        </div>

        <div className={styles.content}>
          <motion.div
            className={styles.mainInfo}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <h1 className={styles.title}>{safeName}</h1>
            <div className={styles.address}>{safeAddress}</div>
          </motion.div>

          <motion.div
            className={styles.metaInfo}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
          >
            <div className={styles.metaItem}>
              <div className={styles.metaIcon} aria-hidden="true">
                <ClockIcon />
              </div>
              <div className={styles.metaText}>
                <div className={styles.metaLabel}>СТАТУС</div>
                <div
                  className={`${styles.metaValue} ${
                    isOpen ? styles.open : styles.closed
                  }`}
                  aria-live="polite"
                  aria-label={statusAriaLabel}
                >
                  {fullStatus}
                </div>
              </div>
            </div>

            <div className={styles.metaItem}>
              <div className={styles.metaIcon} aria-hidden="true">
                <MoneyIcon />
              </div>
              <div className={styles.metaText}>
                <div className={styles.metaLabel}>СРЕДНИЙ ЧЕК</div>
                <div className={styles.metaValue}>{safeAvgCheck}</div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>
    );
  }
);

HeroSection.displayName = "HeroSection";

export default HeroSection;
