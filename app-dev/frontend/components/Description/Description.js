"use client";

import React, { useState, useMemo, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toZonedTime } from "date-fns-tz";
import { useRestaurantStatus } from "@/hooks/useRestaurantStatus";
import styles from "./Description.module.scss";

const IconWrapper = React.memo(({ children, size = 16 }) => (
  <div className={styles.iconWrapper} style={{ width: size, height: size }}>
    {children}
  </div>
));
IconWrapper.displayName = "IconWrapper";

const KitchenIcon = React.memo(() => (
  <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none">
    <rect
      x="3"
      y="3"
      width="18"
      height="18"
      rx="1.5"
      stroke="currentColor"
      strokeWidth="1.5"
    />
    <path
      d="M3 9h18M3 15h18"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
));

const CheckIcon = React.memo(() => (
  <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none">
    <rect
      x="3"
      y="5"
      width="18"
      height="14"
      rx="1.5"
      stroke="currentColor"
      strokeWidth="1.5"
    />
    <circle cx="12" cy="12" r="1.5" fill="currentColor" />
    <path
      d="M7 9V15M17 9V15"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
));

const FeaturesIcon = React.memo(() => (
  <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none">
    <path
      d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
));

const ClockIcon = React.memo(() => (
  <svg width="100%" height="100%" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
    <path
      d="M12 7V12L15 15"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
));

const ChevronIcon = React.memo(({ isOpen }) => (
  <motion.svg
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    animate={{ rotate: isOpen ? 180 : 0 }}
    transition={{ duration: 0.2 }}
  >
    <path
      d="M6 9L12 15L18 9"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </motion.svg>
));

const useCurrentDay = () => {
  const [currentDayName, setCurrentDayName] = useState("ПН");

  useEffect(() => {
    const updateCurrentDay = () => {
      try {
        const moscowTime = toZonedTime(new Date(), "Europe/Moscow"); // ✅ заменили utcToZonedTime
        const dayIndex = moscowTime.getDay();
        const dayNames = ["ВС", "ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ"];
        setCurrentDayName(dayNames[dayIndex]);
      } catch {
        setCurrentDayName("ПН");
      }
    };

    updateCurrentDay();
    const interval = setInterval(updateCurrentDay, 60000);
    return () => clearInterval(interval);
  }, []);

  return currentDayName;
};

const useTextExpansion = (text) => {
  return useMemo(() => {
    const shouldShow = text.length > 200;
    const shortText = shouldShow ? `${text.slice(0, 200).trim()}...` : text;
    return { shortText, shouldShowButton: shouldShow };
  }, [text]);
};

const StatusBadge = React.memo(({ statusInfo }) => {
  return (
    <div className={styles.statusBadge} role="status" aria-live="polite">
      <div
        className={`${styles.statusPill} ${
          statusInfo.isOpen ? styles.open : styles.closed
        }`}
      >
        <div className={styles.statusDot} />
        <span className={styles.statusLabel}>
          {statusInfo.isOpen ? "Открыто" : "Закрыто"}
        </span>
      </div>
    </div>
  );
});

const DescriptionText = React.memo(({ text, shortText, shouldShowButton }) => {
  const [expanded, setExpanded] = useState(false);

  const textVariants = {
    collapsed: { height: "auto", opacity: 1 },
    expanded: { height: "auto", opacity: 1 },
    exit: { opacity: 0, height: 0, transition: { duration: 0.2 } },
  };

  const gradientVariants = {
    collapsed: { opacity: 1, y: 0 },
    expanded: { opacity: 0, y: 10 },
    exit: { opacity: 0 },
  };

  if (!text) {
    return (
      <div className={styles.noDescription}>
        Описание бара пока не добавлено
      </div>
    );
  }

  return (
    <div className={styles.description}>
      <motion.div
        className={styles.textWrapper}
        variants={textVariants}
        initial="collapsed"
        animate={expanded ? "expanded" : "collapsed"}
        exit="exit"
        transition={{
          type: "spring",
          stiffness: 120,
          damping: 20,
          mass: 0.8,
        }}
      >
        <motion.p
          className={styles.text}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
        >
          {expanded ? text : shortText}
        </motion.p>
        <AnimatePresence>
          {!expanded && shouldShowButton && (
            <motion.div
              className={styles.textGradient}
              variants={gradientVariants}
              initial="collapsed"
              animate="collapsed"
              exit="exit"
              transition={{ duration: 0.3, ease: "easeOut" }}
              aria-hidden="true"
            />
          )}
        </AnimatePresence>
      </motion.div>

      {shouldShowButton && (
        <motion.button
          onClick={() => setExpanded(!expanded)}
          className={styles.moreButton}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          transition={{ type: "spring", stiffness: 400, damping: 17 }}
          aria-expanded={expanded}
        >
          {expanded ? "Свернуть" : "Читать больше"}
          <ChevronIcon isOpen={expanded} />
        </motion.button>
      )}
    </div>
  );
});

const RestaurantDetails = React.memo(({ restaurant, currentDayName }) => {
  const { statusInfo, schedule } = useRestaurantStatus(
    restaurant.scheduleItem || []
  );

  const safeKitchen = restaurant.kitchen || "Уточняется";
  const safeAvgCheck = restaurant.avgCheck
    ? `${Number(restaurant.avgCheck).toLocaleString("ru-RU")} ₽`
    : "Уточняется";
  const safeFeatures = Array.isArray(restaurant.features)
    ? restaurant.features.join(", ")
    : restaurant.features || "Нет особенностей";

  const [isScheduleOpen, setIsScheduleOpen] = useState(false);

  const rowVariants = {
    hidden: { opacity: 0, x: -10 },
    visible: { opacity: 1, x: 0, transition: { duration: 0.4 } },
  };

  const scheduleVariants = {
    collapsed: { height: 0, opacity: 0 },
    expanded: { height: "auto", opacity: 1 },
    exit: { height: 0, opacity: 0 },
  };

  const scheduleItemVariants = {
    hidden: { opacity: 0, y: 10 },
    visible: (index) => ({
      opacity: 1,
      y: 0,
      transition: {
        delay: index * 0.1,
        type: "spring",
        stiffness: 100,
        damping: 20,
      },
    }),
    exit: { opacity: 0, y: -10, transition: { duration: 0.2 } },
  };

  const details = [
    {
      icon: <KitchenIcon />,
      label: "Кухня",
      value: safeKitchen,
      delay: 0,
    },
    {
      icon: <CheckIcon />,
      label: "Средний чек",
      value: safeAvgCheck,
      delay: 0.1,
    },
    {
      icon: <FeaturesIcon />,
      label: "Особенности",
      value: safeFeatures,
      delay: 0.2,
    },
  ];

  return (
    <>
      <div className={styles.details} role="list">
        {details.map((detail, index) => (
          <motion.div
            key={detail.label}
            className={styles.detailItem}
            variants={rowVariants}
            initial="hidden"
            animate="visible"
            transition={{ delay: detail.delay }}
            role="listitem"
          >
            <div className={styles.detailContent}>
              <span className={styles.detailLabel}>{detail.label}</span>
              <span className={styles.detailValue}>{detail.value}</span>
            </div>
          </motion.div>
        ))}
      </div>

      <div className={styles.scheduleSection}>
        <div className={styles.scheduleHeader}>
          <StatusBadge statusInfo={statusInfo} />

          <motion.button
            onClick={() => setIsScheduleOpen(!isScheduleOpen)}
            className={styles.scheduleToggle}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            transition={{ type: "spring", stiffness: 400, damping: 17 }}
            aria-expanded={isScheduleOpen}
          >
            <IconWrapper size={16}>
              <ClockIcon />
            </IconWrapper>
            График
            <ChevronIcon isOpen={isScheduleOpen} />
          </motion.button>
        </div>

        <AnimatePresence>
          {isScheduleOpen && (
            <motion.div
              variants={scheduleVariants}
              initial="collapsed"
              animate="expanded"
              exit="exit"
              transition={{
                type: "spring",
                stiffness: 120,
                damping: 20,
                mass: 0.8,
              }}
              className={styles.scheduleDropdown}
            >
              {schedule.map((item, index) => {
                const isCurrentDay = item.day === currentDayName;
                return (
                  <motion.div
                    key={item.day}
                    className={`${styles.scheduleItem} ${
                      isCurrentDay ? styles.currentDay : ""
                    }`}
                    custom={index}
                    variants={scheduleItemVariants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                  >
                    <span className={styles.day}>{item.day}</span>
                    {/* 
                    {isCurrentDay && (
                      <div className={styles.currentIndicator}>Сегодня</div>
                    )}
                      */}
                    <span className={styles.hours}>{item.hours}</span>
                  </motion.div>
                );
              })}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
});

export const Description = React.memo(
  ({ text = "", restaurant = {}, sectionVariants }) => {
    const currentDayName = useCurrentDay();
    const { shortText, shouldShowButton } = useTextExpansion(text);

    return (
      <motion.section
        id="about"
        className={styles.section}
        variants={sectionVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-50px" }}
        role="region"
        aria-labelledby="description-title"
      >
        <div className={styles.header}>
          <h2 id="description-title" className={styles.title}>
            О баре
          </h2>
        </div>

        <div className={styles.content}>
          <DescriptionText
            text={text}
            shortText={shortText}
            shouldShowButton={shouldShowButton}
          />

          <RestaurantDetails
            restaurant={restaurant}
            currentDayName={currentDayName}
          />
        </div>
      </motion.section>
    );
  }
);

Description.displayName = "Description";

export default Description;
