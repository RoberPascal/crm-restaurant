// app/ClientHome.jsx
"use client";

import { motion, AnimatePresence, useScroll } from "framer-motion";
import { useState, useEffect, useCallback, memo } from "react";
import { useTelegram } from "../components/TelegramProvider";
import { Header } from "@/components/Header/Header";
import styles from "./page.module.scss";
import { api } from "@/utils/api";
import dynamic from "next/dynamic";

// Динамический импорт RestaurantCard для избежания проблем с инициализацией
const RestaurantCard = dynamic(
  () => import("@/components/RestaurantCard/RestaurantCard"),
  {
    ssr: false,
  }
);

const SCROLL_THRESHOLD = 10;
const STRAPI_URL = process.env.NEXT_PUBLIC_STRAPI_URL || "";

const MemoizedList = memo(({ restaurants, getImageUrl }) => {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.1, delayChildren: 0.2 },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.5, ease: "easeOut" },
    },
  };

  return (
    <motion.div
      className={styles.restaurantsList}
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      key="list"
    >
      {restaurants.map((restaurant, index) => (
        <motion.div
          key={restaurant.slug || index}
          variants={itemVariants}
          layout
        >
          <RestaurantCard
            restaurant={restaurant}
            isLoading={false}
            imageUrl={getImageUrl(restaurant.image)}
            blurDataURL={restaurant.image?.blurDataURL || ""}
            alt={restaurant.name || "Restaurant image"}
          />
        </motion.div>
      ))}
    </motion.div>
  );
});

MemoizedList.displayName = "MemoizedList";

const ClientHome = memo(({ restaurants }) => {
  const [isHeaderSolid, setIsHeaderSolid] = useState(false);
  const { scrollY } = useScroll();
  const { webApp, user, isTelegram } = useTelegram();

  const getImageUrl = useCallback((imageData) => {
    if (!imageData?.url) return "/default-restaurant.jpg";
    return imageData.url.startsWith("http")
      ? imageData.url
      : `${STRAPI_URL}${imageData.url}`;
  }, []);

  useEffect(() => {
    if (isTelegram && user?.id) {
      const ensureUser = async () => {
        try {
          await api.get("/api/v1/public/me");
          console.log("User ensured in DB:", user.id);
        } catch (error) {
          console.error("Failed to ensure user in DB:", error);
        }
      };
      ensureUser();
    }
  }, [isTelegram, user?.id]);

  useEffect(() => {
    if (webApp) {
      webApp.expand();
      // Опциональные настройки Telegram
    }
  }, [webApp]);

  useEffect(() => {
    let ticking = false;
    const handleScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          setIsHeaderSolid(scrollY.get() >= SCROLL_THRESHOLD);
          ticking = false;
        });
        ticking = true;
      }
    };

    const unsubscribe = scrollY.on("change", handleScroll);
    return () => unsubscribe();
  }, [scrollY]);

  const showEmpty = !restaurants || restaurants.length === 0;
  const showList = restaurants && restaurants.length > 0;

  // ВСЕГДА показываем контент, независимо от пользователя
  return (
    <>
      <Header
        restaurantName={`Добро пожаловать${
          user?.first_name ? `, ${user.first_name}` : ""
        }!`}
        isSolid={isHeaderSolid}
        showBackButton={false}
      />
      <AnimatePresence mode="wait">
        {showEmpty && (
          <motion.div
            className={styles.emptyState}
            role="alert"
            aria-live="polite"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            key="empty"
          >
            <h3>Баров пока нет</h3>
            <p>Скоро здесь появятся новые заведения</p>
          </motion.div>
        )}

        {showList && (
          <MemoizedList
            restaurants={restaurants}
            getImageUrl={getImageUrl}
            key="list"
          />
        )}
      </AnimatePresence>
    </>
  );
});

ClientHome.displayName = "ClientHome";

export default ClientHome;
