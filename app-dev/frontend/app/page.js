// app/page.jsx
import ClientHome from "./ClientHome";
import styles from "./page.module.scss";
import { api } from "@/utils/api";

import "swiper/css";
import "swiper/css/thumbs";
import "swiper/css/zoom";
import "./swiper-custom.css";

// Гарантируем динамический SSR
export const dynamic = "force-dynamic";

// Упрощенная обработка изображений
const processImageData = (imageData, strapiUrl) => {
  if (!imageData) {
    return {
      url: "/default-restaurant.jpg",
      blurDataURL: null,
      name: "Restaurant Image",
    };
  }

  const attributes =
    imageData.data?.attributes || imageData.attributes || imageData;
  const thumbnailPath = attributes?.formats?.thumbnail?.url || attributes?.url;
  const fullPath = attributes?.url;

  const absoluteUrl = fullPath
    ? fullPath.startsWith("http")
      ? fullPath
      : `${strapiUrl}${fullPath}`
    : "/default-restaurant.jpg";

  const blurDataURL = thumbnailPath
    ? thumbnailPath.startsWith("http")
      ? thumbnailPath
      : `${strapiUrl}${thumbnailPath}`
    : null;

  return {
    url: absoluteUrl,
    blurDataURL,
    name: attributes?.name || "Restaurant Image",
  };
};

// Функция для создания/получения пользователя
async function ensureUser() {
  try {
    // Этот вызов автоматически создаст пользователя, если его нет
    const user = await api.get("/api/v1/public/me");
    console.log("User ensured:", user.id);
    return user;
  } catch (error) {
    console.error("Failed to ensure user:", error);
    // Не прерываем загрузку страницы, даже если не удалось создать пользователя
    return null;
  }
}

// Основной fetch данных
async function fetchRestaurants() {
  const STRAPI_BASE_URL = process.env.NEXT_PUBLIC_STRAPI_BASE_URL;
  const STRAPI_API_TOKEN = process.env.STRAPI_API_TOKEN;
  const STRAPI_URL = process.env.NEXT_PUBLIC_STRAPI_URL || STRAPI_BASE_URL;

  if (!STRAPI_BASE_URL || !STRAPI_API_TOKEN) {
    console.error("Missing Strapi configuration");
    return [];
  }

  try {
    const response = await fetch(
      `${STRAPI_BASE_URL}/api/restaurants?populate=*`,
      {
        method: "GET",
        headers: {
          Authorization: `Bearer ${STRAPI_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        next: { revalidate: 60 }, // Ревалидация каждые 60 секунд
      },
    );

    if (!response.ok) {
      console.error("Failed to fetch restaurants:", response.status);
      return [];
    }

    const responseData = await response.json();
    const rawData = Array.isArray(responseData.data) ? responseData.data : [];

    if (rawData.length === 0) return [];

    const normalized = rawData.map((item, index) => {
      const attributes = item.attributes || item;
      const image = processImageData(attributes.image, STRAPI_URL);

      return {
        slug: attributes.slug || `restaurant-${index}`,
        name: attributes.name || "Без названия",
        description: attributes.description || "",
        address: attributes.address || "Адрес уточняется",
        avgCheck: attributes.avgCheck
          ? `${Number(attributes.avgCheck).toLocaleString("ru-RU")} ₽`
          : "Уточняется",
        fullDescription: attributes.fullDescription || "",
        kitchen: attributes.kitchen || "",
        features: attributes.features || "",
        image,
        scheduleItem: Array.isArray(attributes.scheduleItem)
          ? attributes.scheduleItem.map((schedule) => ({
              id: schedule.id || 0,
              dayName: schedule.dayName || "",
              open: schedule.open || "",
              close: schedule.close || "",
            }))
          : [],
        gallery: Array.isArray(attributes.gallery?.data)
          ? attributes.gallery.data.map((galleryItem) => {
              const galleryAttr = galleryItem.attributes || galleryItem;
              const url = galleryAttr.url
                ? galleryAttr.url.startsWith("http")
                  ? galleryAttr.url
                  : `${STRAPI_URL}${galleryAttr.url}`
                : null;
              return {
                id: galleryItem.id || 0,
                url,
              };
            })
          : [],
        location: attributes.location || {},
      };
    });

    return normalized;
  } catch (error) {
    console.error("Error fetching restaurants:", error);
    return [];
  }
}

// Метаданные страницы
export async function generateMetadata() {
  const restaurants = await fetchRestaurants();
  const count = restaurants.length;

  return {
    title: count > 0 ? `Бары (${count}) | Chain` : "Наши бары | Chain",
    description:
      "Сеть уютных баров в Москве. Посетите наши заведения с уникальной атмосферой и изысканной кухней.",
  };
}

// Главная страница
export default async function Home() {
  const restaurants = await fetchRestaurants();

  console.log("Home page loaded with restaurants:", restaurants?.length || 0);

  return (
    <div className={styles.mainContainer}>
      <ClientHome restaurants={restaurants} />
    </div>
  );
}
