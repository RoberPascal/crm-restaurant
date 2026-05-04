// components/RestaurantCard/RestaurantCard.js
"use client";

import React, { useMemo } from "react";
import Link from "next/link";
import Image from "next/image";
import { motion } from "framer-motion";
import { useRestaurantStatus } from "@/hooks/useRestaurantStatus";
import styles from "./RestaurantCard.module.scss";

// Memoized icons
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

const CARD_ANIMATION = { duration: 0.4, ease: "easeOut" };
const HOVER_ANIMATION = { duration: 0.2, ease: "easeOut" };

const RestaurantCard = React.memo(
  ({
    restaurant = {},
    isLoading = false,
    imageUrl = "/default-restaurant.jpg",
    blurDataURL = null,
  }) => {
    const { statusInfo } = useRestaurantStatus(restaurant.scheduleItem || []);

    // Safe handling of props
    const safeName = restaurant.name || "Бар";
    const safeAddress = restaurant.address || "Адрес уточняется";
    const safeDescription = restaurant.description || "Адрес уточняется";
    const safeAvgCheck = useMemo(() => {
      if (!restaurant.avgCheck) return "Уточняется";

      // Если avgCheck уже строка с "₽", убираем её; иначе обрабатываем как число
      const checkValue =
        typeof restaurant.avgCheck === "string"
          ? parseFloat(restaurant.avgCheck.replace(/[^0-9.]/g, "")) // Удаляем всё, кроме цифр и точки
          : Number(restaurant.avgCheck);

      if (isNaN(checkValue)) return "Уточняется";

      return `${checkValue.toLocaleString("ru-RU")} ₽`;
    }, [restaurant.avgCheck]);

    const cardVariants = useMemo(
      () => ({
        hidden: { opacity: 0, y: 20 },
        visible: { opacity: 1, y: 0, transition: CARD_ANIMATION },
        hover: { y: -4, transition: HOVER_ANIMATION },
      }),
      []
    );

    if (isLoading) {
      return (
        <div className={`${styles.card} ${styles.loading}`}>
          <div className={styles.imageWrapper}>
            <div className={styles.imageSkeleton} />
          </div>
          <div className={styles.content}>
            <div className={`${styles.name} ${styles.loadingText}`} />
            <div className={`${styles.address} ${styles.loadingText}`} />
            <div className={styles.metaInfo}>
              <div className={styles.metaItem}>
                <div className={styles.metaIcon} aria-hidden="true">
                  <ClockIcon />
                </div>
                <div className={styles.metaText}>
                  <div
                    className={`${styles.metaLabel} ${styles.loadingText}`}
                  />
                  <div
                    className={`${styles.metaValue} ${styles.loadingText}`}
                  />
                </div>
              </div>
              <div className={styles.metaItem}>
                <div className={styles.metaIcon} aria-hidden="true">
                  <MoneyIcon />
                </div>
                <div className={styles.metaText}>
                  <div
                    className={`${styles.metaLabel} ${styles.loadingText}`}
                  />
                  <div
                    className={`${styles.metaValue} ${styles.loadingText}`}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <motion.div
        variants={cardVariants}
        initial="hidden"
        animate="visible"
        whileHover="hover"
        role="article"
        aria-label={`Бар ${safeName}`}
      >
        <Link
          href={`/restaurant/${restaurant.slug}`}
          className={styles.card}
          prefetch={true}
          aria-label={`Перейти к бару ${safeName}`}
        >
          <div className={styles.imageWrapper}>
            <Image
              src={imageUrl}
              alt={`Интерьер бара ${safeName}`}
              fill
              className={styles.image}
              sizes="(max-width: 768px) 100vw, 50vw"
              priority={false}
              placeholder={blurDataURL ? "blur" : "empty"}
              blurDataURL={blurDataURL}
              quality={85}
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
              <h2 className={styles.name}>{safeName.toUpperCase()}</h2>
              <p className={styles.address}>{safeAddress}</p>
              <p className={styles.description}>{safeDescription}</p>
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
                      statusInfo.isOpen ? styles.open : styles.closed
                    }`}
                    aria-live="polite"
                    aria-label={statusInfo.isOpen ? "Бар открыт" : "Бар закрыт"}
                  >
                    {statusInfo.status.toUpperCase()}
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
        </Link>
      </motion.div>
    );
  }
);

RestaurantCard.displayName = "RestaurantCard";

export default RestaurantCard;
