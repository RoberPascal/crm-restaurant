"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { motion, useInView, AnimatePresence } from "framer-motion";
import Image from "next/image";
import { Swiper, SwiperSlide } from "swiper/react";
import { Navigation, Pagination, Keyboard } from "swiper/modules";
import "swiper/css";
import "swiper/css/navigation";
import "swiper/css/pagination";
import styles from "./Gallery.module.scss";

export const Gallery = React.memo(
  ({
    gallery = [],
    sectionVariants,
    getImageUrl = (img) => img?.url || "/default-gallery.jpg",
  }) => {
    const [selectedImage, setSelectedImage] = useState(null);
    const [currentImageIndex, setCurrentImageIndex] = useState(0);
    const ref = useRef(null);
    const isInView = useInView(ref, { once: true });

    const validImages = gallery.filter(
      (item) => item.image && getImageUrl(item.image),
    );

    const openModal = useCallback((image, index = 0) => {
      setSelectedImage(image);
      setCurrentImageIndex(index);
    }, []);

    const closeModal = useCallback(() => {
      setSelectedImage(null);
      setCurrentImageIndex(0);
    }, []);

    const goToNext = useCallback(() => {
      setCurrentImageIndex((prev) =>
        prev === validImages.length - 1 ? 0 : prev + 1,
      );
    }, [validImages.length]);

    const goToPrev = useCallback(() => {
      setCurrentImageIndex((prev) =>
        prev === 0 ? validImages.length - 1 : prev - 1,
      );
    }, [validImages.length]);

    useEffect(() => {
      const handleEsc = (e) => e.key === "Escape" && closeModal();
      if (selectedImage) {
        document.addEventListener("keydown", handleEsc);
        document.body.style.overflow = "hidden"; // Блокируем скролл
      }
      return () => {
        document.removeEventListener("keydown", handleEsc);
        document.body.style.overflow = "unset";
      };
    }, [selectedImage, closeModal]);

    // Обработчик кликов по оверлею
    const handleOverlayClick = useCallback(
      (e) => {
        if (e.target === e.currentTarget) {
          closeModal();
        }
      },
      [closeModal],
    );

    if (validImages.length === 0) {
      return (
        <motion.section
          id="gallery"
          className={styles.section}
          ref={ref}
          variants={sectionVariants}
          initial="hidden"
          animate={isInView ? "visible" : "hidden"}
          role="region"
          aria-label="Галерея"
        >
          <div className={styles.header}>
            <h2 className={styles.title}>Галерея</h2>
          </div>
          <div className={styles.emptyState}>
            <p>Фотографии скоро появятся</p>
          </div>
        </motion.section>
      );
    }

    return (
      <motion.section
        id="gallery"
        className={styles.section}
        ref={ref}
        variants={sectionVariants}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
        role="region"
        aria-label="Галерея фотографий"
      >
        <div className={styles.header}>
          <h2 className={styles.title}>Галерея</h2>
        </div>

        <div className={`${styles.galleryContainer} gallery-swiper`}>
          <Swiper
            slidesPerView="auto"
            spaceBetween={8}
            grabCursor={true}
            freeMode={true}
            resistanceRatio={0.5}
            className={styles.swiper}
            role="list"
          >
            {validImages.map((item, index) => (
              <SwiperSlide
                key={item.id || index}
                className={styles.imageCard}
                style={{ width: "160px", minWidth: "160px", maxWidth: "160px" }}
              >
                <motion.div
                  role="listitem"
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05, duration: 0.4 }}
                  onClick={() => openModal(item, index)}
                  aria-label={`Фото ${index + 1}`}
                >
                  <Image
                    src={getImageUrl(item.image)}
                    alt={item.image?.name || `Фото ресторана ${index + 1}`}
                    fill
                    sizes="(max-width: 430px) 160px, 180px"
                    className={styles.image}
                    quality={85}
                    loading="lazy"
                    placeholder="blur"
                    blurDataURL={
                      item.image?.blurDataURL ||
                      "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/"
                    }
                  />
                </motion.div>
              </SwiperSlide>
            ))}
          </Swiper>
        </div>

        <AnimatePresence>
          {selectedImage && (
            <motion.div
              className={styles.modalOverlay}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={handleOverlayClick}
              role="dialog"
              aria-modal="true"
            >
              <motion.div
                className={styles.modalContent}
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  className={styles.closeButton}
                  onClick={closeModal}
                  aria-label="Закрыть"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M18 6L6 18M6 6l12 12"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>

                {/* Навигационные кнопки */}
                <button
                  className={`${styles.navButton} ${styles.prevButton}`}
                  onClick={goToPrev}
                  aria-label="Предыдущее фото"
                >
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M15 18l-6-6 6-6"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    ></path>
                  </svg>
                </button>

                <button
                  className={`${styles.navButton} ${styles.nextButton}`}
                  onClick={goToNext}
                  aria-label="Следующее фото"
                >
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M9 18l6-6-6-6"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    ></path>
                  </svg>
                </button>

                {/* Свайпер для модалки */}
                <Swiper
                  modules={[Navigation, Pagination, Keyboard]}
                  initialSlide={currentImageIndex}
                  onSlideChange={(swiper) =>
                    setCurrentImageIndex(swiper.activeIndex)
                  }
                  navigation={{
                    nextEl: `.${styles.nextButton}`,
                    prevEl: `.${styles.prevButton}`,
                  }}
                  pagination={{
                    type: "fraction",
                    el: `.${styles.pagination}`,
                  }}
                  keyboard={{ enabled: true }}
                  className={styles.modalSwiper}
                >
                  {validImages.map((item, index) => (
                    <SwiperSlide key={item.id || index}>
                      <Image
                        src={getImageUrl(item.image)}
                        alt={item.image?.name || `Фото бара ${index + 1}`}
                        width={800}
                        height={600}
                        className={styles.modalImage}
                        quality={90}
                        placeholder="blur"
                        blurDataURL={item.image?.blurDataURL}
                      />
                    </SwiperSlide>
                  ))}
                </Swiper>

                {/* Пагинация */}
                <div className={styles.pagination} />
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.section>
    );
  },
);

Gallery.displayName = "Gallery";
