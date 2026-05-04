// ============================================
// components/Events/Events.js
// ============================================
// Events: Swipeable carousel cards с image/details, arrows, dots. Mobile-touch, no hover.
// Визуал: Gradient cards, icons, staggered fade-in. Tap/focus only.

"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import Image from "next/image";
import styles from "./Events.module.scss";

// Provided icons (with colors from vars)
export const CalendarIcon = ({ className }) => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 20 20"
    fill="none"
    className={className}
    aria-hidden="true"
    role="img"
  >
    <path
      d="M6.66667 1.66667V4.16667M13.3333 1.66667V4.16667M2.5 8.33333H17.5M4.16667 3.33333H15.8333C16.7538 3.33333 17.5 4.07953 17.5 5V16.6667C17.5 17.5871 16.7538 18.3333 15.8333 18.3333H4.16667C3.24619 18.3333 2.5 17.5871 2.5 16.6667V5C2.5 4.07953 3.24619 3.33333 4.16667 3.33333Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const LocationIcon = ({ className }) => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 20 20"
    fill="none"
    className={className}
    aria-hidden="true"
    role="img"
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

/**
 * Events: Single-card swipe carousel с details, arrows, dots.
 * @param {array} props.events - [{id, name, cost, date, location, description, type, ageLimit, image}].
 * @param {object} props.sectionVariants - Motion variants.
 * @param {function} props.getImageUrl - URL resolver.
 * @returns {JSX.Element}
 */
export const Events = React.memo(
  ({
    events = [],
    sectionVariants,
    getImageUrl = (img) => img?.url || "/default-event.jpg",
  }) => {
    const [currentIndex, setCurrentIndex] = useState(0);
    const [startX, setStartX] = useState(0);
    const [isDragging, setIsDragging] = useState(false);
    const containerRef = useRef(null);

    // Mobile-only: 1 card + swipe
    const visibleCards = 1;
    const cardWidth = containerRef.current?.offsetWidth || 0;
    const gap = 0; // No gap for full-width

    // Format date (Oct 02, 2025 — Wednesday)
    const formatDate = useCallback((dateString) => {
      if (!dateString) return null;
      try {
        const date = new Date(dateString);
        return {
          day: date.toLocaleDateString("ru-RU", {
            day: "numeric",
            month: "long",
          }),
          time: date.toLocaleTimeString("ru-RU", {
            hour: "2-digit",
            minute: "2-digit",
          }),
        };
      } catch {
        return null;
      }
    }, []);

    // Fallback image URL
    const getEventImageUrl = useCallback((imageData) => {
      if (!imageData) return null;
      if (imageData.data?.attributes?.url)
        return `${process.env.NEXT_PUBLIC_STRAPI_URL}${imageData.data.attributes.url}`;
      if (imageData.url)
        return `${process.env.NEXT_PUBLIC_STRAPI_URL}${imageData.url}`;
      return null;
    }, []);

    // Touch/drag handlers
    const handleDragStart = useCallback((e) => {
      setIsDragging(true);
      setStartX(e.type.includes("mouse") ? e.clientX : e.touches[0].clientX);
    }, []);

    const handleDragMove = useCallback(
      (e) => {
        if (!isDragging) return;
        const currentX = e.type.includes("mouse")
          ? e.clientX
          : e.touches[0].clientX;
        const diffX = startX - currentX;
        if (Math.abs(diffX) > 50) {
          if (diffX > 0 && currentIndex < events.length - 1)
            setCurrentIndex((prev) => prev + 1);
          else if (diffX < 0 && currentIndex > 0)
            setCurrentIndex((prev) => prev - 1);
          setIsDragging(false);
        }
      },
      [isDragging, startX, currentIndex, events.length],
    );

    const handleDragEnd = useCallback(() => setIsDragging(false), []);

    const goToSlide = useCallback(
      (index) => {
        if (index >= 0 && index < events.length) setCurrentIndex(index);
      },
      [events.length],
    );

    const nextSlide = useCallback(() => {
      if (currentIndex < events.length - 1) setCurrentIndex((prev) => prev + 1);
    }, [currentIndex, events.length]);

    const prevSlide = useCallback(() => {
      if (currentIndex > 0) setCurrentIndex((prev) => prev - 1);
    }, [currentIndex]);

    const carouselOffset = currentIndex * (cardWidth + gap);

    // Если нет событий — ничего не рендерим (после хуков!)
    if (!events.length) return null;

    // Staggered variants для cards
    const cardVariants = {
      hidden: { opacity: 0, x: 20 },
      visible: { opacity: 1, x: 0, transition: { duration: 0.4 } },
    };

    return (
      <motion.section
        id="events"
        className={styles.section}
        variants={sectionVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-100px" }}
        role="region"
        aria-label="Мероприятия"
      >
        <div className={styles.header}>
          <h2 className={styles.title}>Мероприятия</h2>
          <div
            className={styles.controls}
            role="group"
            aria-label="Навигация по мероприятиям"
          >
            <motion.button
              className={`${styles.arrow} ${
                currentIndex === 0 ? styles.disabled : ""
              }`}
              onClick={prevSlide}
              disabled={currentIndex === 0}
              whileTap={{ scale: 0.98 }}
              aria-label="Предыдущее мероприятие"
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M15 18L9 12L15 6"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </motion.button>
            <motion.button
              className={`${styles.arrow} ${
                currentIndex >= events.length - 1 ? styles.disabled : ""
              }`}
              onClick={nextSlide}
              disabled={currentIndex >= events.length - 1}
              whileTap={{ scale: 0.98 }}
              aria-label="Следующее мероприятие"
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M9 18L15 12L9 6"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </motion.button>
          </div>
        </div>

        <div
          className={styles.carouselContainer}
          ref={containerRef}
          onMouseDown={handleDragStart}
          onMouseMove={handleDragMove}
          onMouseUp={handleDragEnd}
          onMouseLeave={handleDragEnd}
          onTouchStart={handleDragStart}
          onTouchMove={handleDragMove}
          onTouchEnd={handleDragEnd}
          role="region"
          aria-label="Карусель мероприятий"
        >
          <motion.div
            className={styles.carousel}
            style={{ transform: `translateX(-${carouselOffset}px)` }}
            role="list"
            variants={cardVariants}
            initial="hidden"
            animate="visible"
          >
            {events.map((event, index) => {
              const imgUrl =
                getImageUrl(event.image) || getEventImageUrl(event.image);
              const formattedDate = formatDate(event.date);

              return (
                <div
                  key={event.id || index}
                  className={styles.card}
                  style={{ width: `${cardWidth}px` }}
                  role="listitem"
                  aria-label={`${event.name}, ${
                    formattedDate ? formattedDate.day : "Дата уточняется"
                  }`}
                >
                  <div className={styles.imageWrapper}>
                    {imgUrl ? (
                      <>
                        <Image
                          src={imgUrl}
                          alt={event.name}
                          fill
                          style={{ objectFit: "cover" }}
                          className={styles.image}
                          placeholder="blur"
                          blurDataURL={
                            event.image?.blurDataURL ||
                            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8//hlAADeAAlQ+6mJAAAAAElFTkSuQmCC"
                          }
                        />
                        <div className={styles.overlay}>
                          {event.type && (
                            <div
                              className={styles.type}
                              aria-label={`Тип: ${event.type}`}
                            >
                              {event.type}
                            </div>
                          )}
                          {event.ageLimit && (
                            <div
                              className={styles.age}
                              aria-label={`Возраст: ${event.ageLimit}+`}
                            >
                              {event.ageLimit}+
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      <div
                        className={styles.placeholder}
                        aria-label={event.name}
                      >
                        {event.name}
                      </div>
                    )}
                  </div>

                  <div className={styles.details}>
                    <div className={styles.eventHeader}>
                      <h3 className={styles.name}>{event.name}</h3>
                      {event.cost && (
                        <div
                          className={styles.cost}
                          aria-label={`Стоимость: ${event.cost} ₽`}
                        >
                          {event.cost} ₽
                        </div>
                      )}
                    </div>

                    {formattedDate && (
                      <div
                        className={styles.dateTime}
                        role="group"
                        aria-label="Дата и время"
                      >
                        <CalendarIcon className={styles.icon} />
                        <span className={styles.date}>{formattedDate.day}</span>
                        <span className={styles.time}>
                          {formattedDate.time}
                        </span>
                      </div>
                    )}
                    {event.location && (
                      <div
                        className={styles.location}
                        role="group"
                        aria-label="Место проведения"
                      >
                        <LocationIcon className={styles.icon} />
                        <span>{event.location}</span>
                      </div>
                    )}
                    {event.description && (
                      <p className={styles.description}>{event.description}</p>
                    )}
                  </div>
                </div>
              );
            })}
          </motion.div>
        </div>

        {events.length > 1 && (
          <div
            className={styles.pagination}
            role="tablist"
            aria-label="Пагинация мероприятий"
          >
            {Array.from({ length: events.length }).map((_, index) => (
              <motion.button
                key={index}
                className={`${styles.paginationDot} ${
                  index === currentIndex ? styles.active : ""
                }`}
                onClick={() => goToSlide(index)}
                aria-label={`Перейти к мероприятию ${index + 1}`}
                whileTap={{ scale: 0.9 }}
                role="tab"
                aria-selected={index === currentIndex}
              />
            ))}
          </div>
        )}
      </motion.section>
    );
  },
);

Events.displayName = "Events";
