// app/components/MenuModal.jsx
"use client";

import React, { useCallback, useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Image from "next/image";
import { Swiper, SwiperSlide } from "swiper/react";
import {
  Navigation,
  Pagination,
  Zoom,
  Keyboard,
  Thumbs,
  FreeMode,
} from "swiper/modules";
import "swiper/css";
import "swiper/css/navigation";
import "swiper/css/pagination";
import "swiper/css/zoom";
import "swiper/css/free-mode";
import "swiper/css/thumbs";
import styles from "./MenuModal.module.scss";

const CloseIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M18 6L6 18M6 6l12 12"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const ChevronIcon = ({ direction = "left" }) => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <path
      d={direction === "left" ? "M15 18l-6-6 6-6" : "M9 18l6-6-6-6"}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const MenuModal = ({
  isOpen,
  onClose,
  menuGallery = [],
  getImageUrl,
}) => {
  const [thumbsSwiper, setThumbsSwiper] = useState(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const mainSwiperRef = useRef(null);
  const modalRef = useRef(null);
  const prevRef = useRef(null);
  const nextRef = useRef(null);
  const paginationRef = useRef(null);

  // Блокировка скролла body при открытии
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      document.body.style.position = "fixed";
      document.body.style.width = "100%";
      document.body.style.top = `-${window.scrollY}px`;
    } else {
      const scrollY = document.body.style.top;
      document.body.style.overflow = "";
      document.body.style.position = "";
      document.body.style.width = "";
      document.body.style.top = "";
      window.scrollTo(0, parseInt(scrollY || "0") * -1);
    }

    return () => {
      document.body.style.overflow = "";
      document.body.style.position = "";
      document.body.style.width = "";
      document.body.style.top = "";
    };
  }, [isOpen]);

  // Уничтожение Swiper при закрытии модала
  useEffect(() => {
    if (!isOpen) {
      if (mainSwiperRef.current && !mainSwiperRef.current.destroyed) {
        mainSwiperRef.current.destroy(true, true);
        mainSwiperRef.current = null;
      }
      if (thumbsSwiper && !thumbsSwiper.destroyed) {
        thumbsSwiper.destroy(true, true);
        setThumbsSwiper(null);
      }
    }
  }, [isOpen, thumbsSwiper]);

  // Обработчик клавиатуры
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;

      switch (e.key) {
        case "Escape":
          onClose();
          break;
        case "ArrowLeft":
          mainSwiperRef.current?.slidePrev();
          break;
        case "ArrowRight":
          mainSwiperRef.current?.slideNext();
          break;
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Сброс состояния при закрытии
  useEffect(() => {
    if (!isOpen) {
      setActiveIndex(0);
      setIsLoading(true);
      setThumbsSwiper(null); // Сбрасываем thumbsSwiper при закрытии
    }
  }, [isOpen]);

  const handleImageLoad = useCallback(() => setIsLoading(false), []);

  const modalVariants = {
    hidden: { opacity: 0, scale: 0.8, y: 30 },
    visible: { opacity: 1, scale: 1, y: 0, transition: { duration: 0.5 } },
    exit: { opacity: 0, scale: 0.8, y: 30, transition: { duration: 0.3 } },
  };

  const backdropVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1 },
    exit: { opacity: 0 },
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        className={styles.modalBackdrop}
        variants={backdropVariants}
        initial="hidden"
        animate="visible"
        exit="exit"
        onClick={onClose}
      >
        <motion.div
          ref={modalRef}
          className={styles.modalContent}
          variants={modalVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          onClick={(e) => e.stopPropagation()}
        >
          <div className={styles.modalHeader}>
            <h2 className={styles.modalTitle}>Меню</h2>
            <button
              className={styles.closeButton}
              onClick={onClose}
              aria-label="Закрыть меню"
            >
              <CloseIcon />
            </button>
          </div>

          <div className={styles.mainContent}>
            {menuGallery.length === 0 ? (
              <div className={styles.emptyState}>
                <p>Меню временно недоступно</p>
              </div>
            ) : (
              <>
                <div className={styles.mainSwiperContainer}>
                  <Swiper
                    modules={[Navigation, Pagination, Zoom, Keyboard, Thumbs]}
                    thumbs={{
                      swiper:
                        thumbsSwiper && !thumbsSwiper.destroyed
                          ? thumbsSwiper
                          : null,
                    }}
                    navigation={{
                      prevEl: prevRef.current,
                      nextEl: nextRef.current,
                    }}
                    pagination={{
                      type: "fraction",
                      el: paginationRef.current,
                    }}
                    zoom={{ maxRatio: 3, minRatio: 1 }}
                    keyboard={{ enabled: true }}
                    spaceBetween={0}
                    slidesPerView={1}
                    onBeforeInit={(swiper) => {
                      if (prevRef.current)
                        swiper.params.navigation.prevEl = prevRef.current;
                      if (nextRef.current)
                        swiper.params.navigation.nextEl = nextRef.current;
                      if (paginationRef.current)
                        swiper.params.pagination.el = paginationRef.current;
                    }}
                    onSlideChange={(swiper) =>
                      setActiveIndex(swiper.activeIndex)
                    }
                    onSwiper={(swiper) => {
                      mainSwiperRef.current = swiper;
                      setIsLoading(false);
                    }}
                    className={styles.mainSwiper}
                  >
                    {menuGallery.map((item, index) => (
                      <SwiperSlide
                        key={item.id || index}
                        className={styles.mainSlide}
                      >
                        <div
                          className={`swiper-zoom-container ${styles.zoomContainer}`}
                        >
                          <Image
                            src={getImageUrl(item.image)}
                            alt={`Страница меню ${index + 1}`}
                            fill
                            sizes="(max-width: 430px) 100vw, 430px"
                            className={styles.mainImage}
                            quality={95}
                            placeholder={item.blurDataURL ? "blur" : "empty"}
                            blurDataURL={item.blurDataURL}
                            onLoad={handleImageLoad}
                            priority={index === 0}
                          />
                          {isLoading && index === activeIndex && (
                            <div className={styles.loading}>
                              <p>Загрузка...</p>
                            </div>
                          )}
                        </div>
                      </SwiperSlide>
                    ))}
                  </Swiper>

                  {menuGallery.length > 1 && (
                    <>
                      <button
                        ref={prevRef}
                        className={styles.navPrev}
                        aria-label="Предыдущее изображение"
                      >
                        <ChevronIcon direction="left" />
                      </button>
                      <button
                        ref={nextRef}
                        className={styles.navNext}
                        aria-label="Следующее изображение"
                      >
                        <ChevronIcon direction="right" />
                      </button>
                    </>
                  )}

                  {menuGallery.length > 1 && (
                    <div className={styles.paginationContainer}>
                      <div ref={paginationRef} className={styles.pagination} />
                    </div>
                  )}
                </div>

                {menuGallery.length > 1 && (
                  <div className={styles.thumbnailsContainer}>
                    <Swiper
                      modules={[FreeMode, Thumbs]}
                      onSwiper={(swiper) => {
                        if (!swiper.destroyed) setThumbsSwiper(swiper);
                      }}
                      watchSlidesProgress
                      freeMode={true}
                      spaceBetween={8}
                      slidesPerView="auto"
                      centeredSlides={false}
                      className={styles.thumbnailsSwiper}
                    >
                      {menuGallery.map((item, index) => (
                        <SwiperSlide
                          key={item.id || index}
                          className={`${styles.thumbnailSlide} ${
                            index === activeIndex
                              ? styles.thumbnailSlideActive
                              : ""
                          }`}
                        >
                          <div className={styles.thumbnailWrapper}>
                            <Image
                              src={getImageUrl(item.image)}
                              alt={`Миниатюра ${index + 1}`}
                              fill
                              sizes="68px"
                              className={styles.thumbnailImage}
                              quality={40}
                            />
                            <div className={styles.thumbnailOverlay} />
                          </div>
                        </SwiperSlide>
                      ))}
                    </Swiper>
                  </div>
                )}
              </>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

MenuModal.displayName = "MenuModal";
