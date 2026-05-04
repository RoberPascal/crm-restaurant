// app/restaurant/[slug]/ClientPage.js
"use client";

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
} from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { useRestaurantStatus } from "@/hooks/useRestaurantStatus";
import { Header } from "@/components/Header/Header";
import HeroSection from "@/components/HeroSection/HeroSection";
import { Gallery } from "@/components/Gallery/Gallery";
import { MenuSection } from "@/components/MenuSection/MenuSection";
import { MenuModal } from "@/components/MenuModal/MenuModal";
import { Description } from "@/components/Description/Description";
import { YandexMap } from "@/components/YandexMap/YandexMap";
import { useTelegram } from "@/components/TelegramProvider";
import styles from "./RestaurantPage.module.scss";
import dynamic from "next/dynamic";

// Динамический импорт BookingModal для избежания проблем с инициализацией
const BookingModal = dynamic(
  () => import("@/components/BookingModal/BookingModal"),
  {
    ssr: false,
    loading: () => null,
  },
);

const STRAPI_URL =
  process.env.NEXT_PUBLIC_STRAPI_URL ||
  process.env.NEXT_PUBLIC_STRAPI_BASE_URL ||
  "";
const DEFAULT_SCHEDULE = [
  { dayName: "ПН", open: "13:00:00", close: "23:00:00" },
  { dayName: "ВТ", open: "13:00:00", close: "23:00:00" },
  { dayName: "СР", open: "13:00:00", close: "23:00:00" },
  { dayName: "ЧТ", open: "13:00:00", close: "23:00:00" },
  { dayName: "ПТ", open: "13:00:00", close: "23:00:00" },
  { dayName: "СБ", open: "12:00:00", close: "00:00:00" },
  { dayName: "ВС", open: "12:00:00", close: "00:00:00" },
];
const SECTION_IDS = ["bron", "gallery", "menu", "about", "map"];
const IS_DEVELOPMENT = process.env.NEXT_PUBLIC_ENV === "development";

// Компактная иконка маршрута
const RouteIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    version="1.0"
    width="1024.000000pt"
    height="1024.000000pt"
    viewBox="0 0 1024.000000 1024.000000"
    preserveAspectRatio="xMidYMid meet"
  >
    <g
      transform="translate(0.000000,1024.000000) scale(0.100000,-0.100000)"
      fill="#000000"
      stroke="none"
    >
      <path d="M2676 8695 c-320 -46 -600 -186 -826 -414 -218 -220 -362 -504 -406 -802 -22 -153 -15 -432 16 -564 77 -339 237 -636 620 -1150 227 -305 587 -709 704 -790 72 -49 127 -56 193 -24 129 62 602 592 905 1015 275 385 414 661 480 958 20 87 23 129 23 311 0 234 -10 300 -70 482 -118 355 -375 649 -722 828 -103 53 -268 109 -403 136 -129 26 -382 33 -514 14z m504 -375 c371 -89 679 -369 801 -726 102 -302 72 -629 -86 -944 -148 -295 -507 -788 -883 -1213 l-105 -119 -61 68 c-268 297 -611 743 -791 1029 -316 503 -369 928 -164 1336 70 141 226 321 353 408 118 82 312 156 471 180 109 17 358 7 465 -19z" />
      <path d="M2785 7864 c-163 -39 -250 -82 -333 -165 -164 -162 -229 -371 -189 -604 48 -275 273 -486 561 -526 251 -35 498 77 637 289 139 212 138 497 -2 707 -128 191 -314 293 -544 301 -60 1 -119 1 -130 -2z m232 -365 c72 -28 144 -94 180 -167 69 -142 7 -321 -135 -392 -69 -35 -196 -40 -274 -11 -198 75 -257 342 -110 494 36 38 93 73 142 88 50 15 138 9 197 -12z" />
      <path d="M6985 6530 c-508 -78 -931 -477 -1053 -992 -23 -100 -26 -134 -27 -298 0 -119 5 -210 14 -255 99 -501 490 -896 989 -1000 40 -8 84 -15 98 -15 l24 0 0 -652 c0 -775 -2 -799 -98 -982 -151 -290 -463 -456 -784 -417 -282 34 -504 192 -628 446 -77 159 -73 111 -80 965 -7 831 -4 792 -64 940 -102 250 -337 439 -615 495 -104 21 -333 16 -426 -10 -253 -70 -450 -261 -536 -520 -23 -69 -23 -79 -29 -605 l-5 -535 -28 -56 c-36 -75 -107 -140 -183 -168 -49 -19 -73 -22 -144 -19 -142 7 -233 65 -295 189 -39 75 -44 191 -45 860 l0 576 -22 33 c-45 65 -106 90 -183 76 -48 -9 -112 -68 -125 -114 -14 -52 -13 -1286 1 -1388 47 -337 333 -577 689 -577 207 0 343 56 486 198 94 94 132 154 175 275 23 64 24 75 29 590 6 569 5 553 64 655 34 57 117 132 179 160 114 52 288 54 420 5 129 -48 235 -163 277 -297 19 -62 20 -92 20 -717 0 -363 5 -698 10 -758 33 -343 230 -675 513 -862 322 -214 772 -244 1124 -77 300 144 530 422 622 752 37 134 41 224 41 890 l0 646 53 7 c371 49 740 317 925 676 101 193 144 369 144 590 0 216 -42 394 -139 585 -62 125 -120 203 -237 323 -198 203 -445 334 -706 377 -100 16 -354 19 -445 5z m345 -341 c97 -12 237 -56 321 -100 159 -85 313 -248 400 -424 65 -134 89 -230 96 -387 9 -197 -19 -328 -106 -495 -124 -238 -385 -425 -667 -479 -119 -22 -327 -15 -434 16 -359 102 -617 395 -671 762 -16 112 -7 323 19 420 94 351 380 618 730 682 96 17 202 19 312 5z" />
    </g>
  </svg>
);

/**
 * Memoized section component
 */
const MemoizedSection = React.memo(({ children, id, variants }) => (
  <motion.section
    key={id}
    id={id}
    className={styles.section}
    variants={variants}
    initial="hidden"
    whileInView="visible"
    viewport={{ once: true, margin: "-100px" }}
  >
    {children}
  </motion.section>
));

/**
 * Constructs image URL
 */
function getImageUrl(imageData) {
  if (!imageData?.url) {
    return "/default-restaurant.jpg";
  }
  return imageData.url.startsWith("/")
    ? `${STRAPI_URL}${imageData.url}`
    : imageData.url;
}

/**
 * Client-side restaurant page
 */
export default function ClientPage({ restaurant, slug }) {
  const { webApp, user: telegramUser } = useTelegram();

  // В dev-режиме используем мокнутого пользователя
  const effectiveUser = IS_DEVELOPMENT
    ? { first_name: "Developer", id: 123456 }
    : telegramUser;

  const [menuOpen, setMenuOpen] = useState(false);
  const [bookingOpen, setBookingOpen] = useState(false);
  const [selectedBookingTime, setSelectedBookingTime] = useState(null);
  const [selectedBookingDate, setSelectedBookingDate] = useState(new Date());
  const [activeSection, setActiveSection] = useState("");

  const heroRef = useRef(null);
  const { scrollY } = useScroll();
  const heroTranslateY = useTransform(scrollY, [0, 300], [0, 60]);

  const { statusInfo } = useRestaurantStatus(
    restaurant.scheduleItem?.length > 0
      ? restaurant.scheduleItem
      : DEFAULT_SCHEDULE,
  );

  const handleTimeSelect = useCallback((time, date) => {
    setSelectedBookingTime(time);
    setSelectedBookingDate(new Date(date));
    setBookingOpen(true);
  }, []);

  const openMenuModal = useCallback(() => setMenuOpen(true), []);
  const closeMenuModal = useCallback(() => setMenuOpen(false), []);
  const openBookingModal = useCallback(() => setBookingOpen(true), []);
  const closeBookingModal = useCallback(() => setBookingOpen(false), []);

  // Функция для открытия Яндекс.Карт с маршрутом
  const openYandexMaps = useCallback(() => {
    const { location } = restaurant;
    if (!location?.lat || !location?.lng) {
      console.error("Координаты бара не указаны");
      return;
    }

    const lat = Number(location.lat);
    const lng = Number(location.lng);

    // Формируем URL для Яндекс.Карт с прокладкой маршрута
    const yandexMapsUrl = `https://yandex.ru/maps/?rtext=~${lat},${lng}&rtt=auto`;

    window.open(yandexMapsUrl, "_blank", "noopener,noreferrer");
  }, [restaurant]);

  useEffect(() => {
    if (webApp && !IS_DEVELOPMENT) {
      webApp.expand();

      document.body.style.backgroundColor =
        webApp.themeParams.bg_color || "#ffffff";
      document.body.style.color = webApp.themeParams.text_color || "#000000";

      if (webApp.initData) {
        const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
        if (apiBase) {
          fetch(`${apiBase}/validate-telegram`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ initData: webApp.initData }),
          }).catch(() => {});
        }
      }

      webApp.MainButton.setText("Забронировать").show();
      const handleMainButton = () => openBookingModal();
      webApp.MainButton.onClick(handleMainButton);

      return () => {
        webApp.MainButton.offClick(handleMainButton);
        webApp.MainButton.hide();
      };
    } else if (IS_DEVELOPMENT) {
      console.log("Dev mode: Skipping real Telegram setup");
    }
  }, [webApp, openBookingModal]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActiveSection(entry.target.id);
        });
      },
      { threshold: 0.1, rootMargin: "-100px 0px 0px 0px" },
    );

    SECTION_IDS.forEach((id) => {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    });

    return () => observer.disconnect();
  }, []);

  const sectionVariants = useMemo(
    () => ({
      hidden: { opacity: 0, y: 20 },
      visible: {
        opacity: 1,
        y: 0,
        transition: { duration: 0.6, ease: "easeOut" },
      },
    }),
    [],
  );

  const restaurantData = useMemo(
    () => ({
      ...restaurant,
      heroImageUrl: getImageUrl(restaurant.image),
    }),
    [restaurant],
  );

  // === Гибкая проверка доступа ===
  if (!effectiveUser) {
    return (
      <div className={styles.mainContainer}>
        <Header restaurantName={restaurantData.name} showBackButton={true} />
        <motion.div
          className={styles.emptyState}
          role="alert"
          aria-live="polite"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          key="empty"
        >
          <h3>Доступ ограничен</h3>
          <p>
            {IS_DEVELOPMENT
              ? "В режиме разработки Telegram не требуется. Перезагрузите страницу."
              : "Пожалуйста, откройте приложение через Telegram"}
          </p>
          {IS_DEVELOPMENT && (
            <p style={{ fontSize: "0.8rem", color: "#666", marginTop: "10px" }}>
              Вы вошли как Developer (dev mode)
            </p>
          )}
        </motion.div>
      </div>
    );
  }

  return (
    <>
      <Header restaurantName={restaurantData.name} showBackButton={true} />
      <HeroSection
        restaurant={restaurantData}
        heroRef={heroRef}
        heroTranslateY={heroTranslateY}
        isOpen={statusInfo.isOpen}
        imageUrl={restaurantData.heroImageUrl}
        blurDataURL={restaurant.image?.blurDataURL}
      />
      <div className={styles.content}>
        <Description
          text={restaurantData.fullDescription}
          restaurant={restaurantData}
          sectionVariants={sectionVariants}
        />
        <MemoizedSection id="gallery" variants={sectionVariants}>
          <Gallery gallery={restaurantData.gallery} getImageUrl={getImageUrl} />
        </MemoizedSection>
        <MemoizedSection id="menu" variants={sectionVariants}>
          <MenuSection
            menuItems={restaurantData.menuItems}
            menuGallery={restaurantData.menuGallery}
            onMenuButtonClick={openMenuModal}
            sectionVariants={sectionVariants}
            getImageUrl={getImageUrl}
          />
        </MemoizedSection>
        <MemoizedSection id="map" variants={sectionVariants}>
          <YandexMap
            location={restaurantData.location}
            restaurant={restaurantData}
            sectionVariants={sectionVariants}
          />
        </MemoizedSection>
        <p className={styles.made}>
          Разработано в{" "}
          <a
            href="https://t.me/hellobotstudioo"
            target="_blank"
            rel="noopener noreferrer"
          >
            hello-bot
          </a>
        </p>

        {/* Обновленная секция с кнопкой маршрута справа */}
        <motion.div
          className={styles.actionsWrapper}
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, type: "spring", stiffness: 80 }}
        >
          <div className={styles.actionsContainer}>
            <motion.button
              onClick={openBookingModal}
              className={styles.bookButton}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              role="button"
              aria-label="Забронировать стол"
            >
              Забронировать
            </motion.button>

            <motion.button
              onClick={openYandexMaps}
              className={styles.routeButton}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              role="button"
              aria-label="Построить маршрут в Яндекс Картах"
              disabled={
                !restaurantData.location?.lat || !restaurantData.location?.lng
              }
            >
              <RouteIcon />
            </motion.button>
          </div>
        </motion.div>
      </div>
      <MenuModal
        isOpen={menuOpen}
        onClose={closeMenuModal}
        menuGallery={restaurantData.menuGallery}
        getImageUrl={getImageUrl}
      />
      <BookingModal
        isOpen={bookingOpen}
        onClose={closeBookingModal}
        restaurant={restaurantData}
        preselectedTime={selectedBookingTime}
        preselectedDate={selectedBookingDate}
        restaurantSlug={slug}
        hallMap={restaurant.hallMap}
        tables={restaurant.tables}
      />
    </>
  );
}
