// MenuSection.jsx
"use client";

import React, { memo, useEffect, useState } from "react";
import { motion } from "framer-motion";
import Image from "next/image";
import { Swiper, SwiperSlide } from "swiper/react";
import "swiper/css";
import styles from "./MenuSection.module.scss";

const PlateIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
    <path
      d="M12 7v10M7 12h10"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);

const RubleIcon = () => (
  <svg
    width="12"
    height="12"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M8 7h5a3 3 0 010 6H8m0-6v6m0 0v4m0-4h7"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);

export const MenuSection = memo(
  ({
    menuItems = [],
    menuGallery = [],
    onMenuButtonClick,
    sectionVariants,
    getImageUrl,
  }) => {
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
      setIsLoading(true);
      const timer = setTimeout(() => setIsLoading(false), 600);
      return () => clearTimeout(timer);
    }, [menuItems.length, menuGallery.length]);

    const itemVariants = {
      hidden: { opacity: 0, x: 20 },
      visible: (i) => ({
        opacity: 1,
        x: 0,
        transition: { delay: i * 0.02, duration: 0.3 },
      }),
    };

    if (isLoading) {
      return (
        <motion.section
          id="menu"
          className={styles.section}
          variants={sectionVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-50px" }}
          role="region"
          aria-label="Меню"
        >
          <div className={styles.header}>
            <h2 className={styles.title}>Меню</h2>
          </div>
          <div className={styles.loader}>
            <div className={styles.spinner} aria-hidden="true" />
          </div>
        </motion.section>
      );
    }

    return (
      <motion.section
        id="menu"
        className={styles.section}
        variants={sectionVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-50px" }}
        role="region"
        aria-label="Меню бара"
      >
        <div className={styles.header}>
          <h2 className={styles.title}>Меню</h2>
        </div>
        <div className={styles.content}>
          {menuItems.length === 0 ? (
            <div className={styles.emptyState}>
              <PlateIcon />
              <p>Меню обновляется</p>
            </div>
          ) : (
            <>
              <div className={`${styles.galleryContainer} menu-swiper`}>
                {" "}
                {/* Unique wrapper class */}
                <Swiper
                  slidesPerView="auto"
                  spaceBetween={8}
                  grabCursor={true}
                  freeMode={true}
                  resistanceRatio={0.5}
                  className={styles.swiper}
                  role="list"
                >
                  {menuItems.map((item, index) => (
                    <SwiperSlide
                      key={item.id || index}
                      className={styles.swiperSlide}
                      style={{
                        width: "160px",
                        minWidth: "160px",
                        maxWidth: "160px",
                      }} // Inline fallback
                    >
                      <motion.div
                        className={styles.itemCard}
                        variants={itemVariants}
                        custom={index}
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05, duration: 0.4 }}
                        role="listitem"
                      >
                        <div className={styles.imageWrapper}>
                          {item.image?.url ? (
                            <Image
                              src={getImageUrl(item.image)}
                              alt={item.name}
                              fill
                              sizes="(max-width: 430px) 160px, 160px"
                              className={styles.image}
                              quality={85}
                              placeholder={
                                item.image.blurDataURL ? "blur" : "empty"
                              }
                              blurDataURL={item.image.blurDataURL}
                            />
                          ) : (
                            <div className={styles.placeholderImage}>
                              <PlateIcon />
                            </div>
                          )}
                        </div>
                        <div className={styles.itemInfo}>
                          <h3 className={styles.itemName}>{item.name}</h3>
                          <div className={styles.price}>
                            <span>
                              {Number(item.price).toLocaleString("ru-RU")}
                            </span>
                            <mark>₽</mark>
                          </div>
                        </div>
                      </motion.div>
                    </SwiperSlide>
                  ))}
                </Swiper>
              </div>
              {menuGallery.length > 0 && (
                <motion.button
                  onClick={onMenuButtonClick}
                  className={styles.menuButton}
                  whileTap={{ scale: 0.95 }}
                  aria-label="Открыть полное меню"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.3 }}
                >
                  <span>Полное меню</span>
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path
                      d="M9 18l6-6-6-6"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </motion.button>
              )}
            </>
          )}
        </div>
      </motion.section>
    );
  }
);

MenuSection.displayName = "MenuSection";
