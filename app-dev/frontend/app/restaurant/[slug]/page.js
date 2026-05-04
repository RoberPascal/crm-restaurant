// app/restaurant/[slug]/page.js
import { notFound } from "next/navigation";
import { Suspense } from "react";
import ClientPage from "./ClientPage";
import ErrorFallback from "./ErrorFallback";
import styles from "./RestaurantPage.module.scss";
import { z } from "zod";

import "swiper/css";
import "swiper/css/thumbs";
import "swiper/css/zoom";
import "../../../app/swiper-custom.css";

const BLUR_CACHE_MAX_SIZE = 100;
const blurCache = new Map();
const metadataCache = new Map();

/**
 * Generates a blurDataURL for an image (фикс для Edge: без Buffer, используем btoa)
 */
async function getBlurDataURL(thumbnailPath, strapiUrl) {
  if (!thumbnailPath) return null;
  const cacheKey = `${strapiUrl}${thumbnailPath}`;
  if (blurCache.has(cacheKey)) return blurCache.get(cacheKey);

  try {
    const response = await fetch(cacheKey, { cache: "force-cache" });
    if (!response.ok) return null;

    const buffer = await response.arrayBuffer();
    const base64 = btoa(
      Array.from(new Uint8Array(buffer))
        .map((byte) => String.fromCharCode(byte))
        .join("")
    );
    const blurData = `data:image/jpeg;base64,${base64}`;

    if (blurCache.size >= BLUR_CACHE_MAX_SIZE) {
      const oldestKey = blurCache.keys().next().value;
      blurCache.delete(oldestKey);
    }
    blurCache.set(cacheKey, blurData);
    return blurData;
  } catch {
    return null;
  }
}

/**
 * Processes image data from Strapi
 */
async function processImageData(imageData, strapiUrl) {
  if (!imageData) return null;

  const imageAttributes =
    imageData.data?.attributes || imageData.attributes || imageData;

  if (!imageAttributes?.url) return null;

  const thumbnailPath =
    imageAttributes.formats?.thumbnail?.url || imageAttributes.url;
  const fullPath = imageAttributes.formats?.medium?.url || imageAttributes.url;
  const absoluteUrl = fullPath.startsWith("http")
    ? fullPath
    : `${strapiUrl}${fullPath}`;
  const blurDataURL = await getBlurDataURL(thumbnailPath, strapiUrl);

  return {
    id: imageData.id || imageAttributes.id,
    url: absoluteUrl,
    name: imageAttributes.name || "",
    blurDataURL,
    width: imageAttributes.width || 0,
    height: imageAttributes.height || 0,
  };
}

/**
 * Processes gallery data
 */
async function processGallery(galleryData, strapiUrl) {
  if (!galleryData) return [];

  const galleryItems = galleryData.data || galleryData;
  if (!Array.isArray(galleryItems)) return [];

  const validItems = galleryItems.filter((item) => item !== null);
  return Promise.all(
    validItems.map(async (item) => ({
      id: item.id,
      image: await processImageData(item, strapiUrl),
    }))
  );
}

/**
 * Processes menu items
 */
async function processMenuItems(menuItems, strapiUrl) {
  if (!menuItems) return [];

  const menuItemsArray = menuItems.data || menuItems;
  if (!Array.isArray(menuItemsArray)) return [];

  return Promise.all(
    menuItemsArray.map(async (item) => {
      const attributes = item.attributes || item;
      return {
        id: item.id,
        name: attributes.name || "",
        price: attributes.price || 0,
        image: attributes.image
          ? await processImageData(attributes.image, strapiUrl)
          : null,
      };
    })
  );
}

/**
 * Processes menu gallery
 */
async function processMenuGallery(menuGallery, strapiUrl) {
  if (!menuGallery) return [];

  const menuGalleryArray = menuGallery.data || menuGallery;
  if (!Array.isArray(menuGalleryArray)) return [];

  const validItems = menuGalleryArray.filter((item) => item !== null);
  return Promise.all(
    validItems.map(async (item) => {
      const attributes = item.attributes || item;
      return {
        id: item.id,
        name: attributes.name || `Menu image ${item.id}`,
        image: await processImageData(item, strapiUrl),
      };
    })
  );
}

/**
 * Processes schedule data
 */
function processSchedule(scheduleData) {
  if (!scheduleData) return [];

  const scheduleArray = scheduleData.data || scheduleData;
  if (!Array.isArray(scheduleArray)) return [];

  return scheduleArray.map((item) => {
    const attributes = item.attributes || item;
    return {
      id: item.id || 0,
      dayName: attributes.dayName || "",
      open: attributes.open || "",
      close: attributes.close || "",
    };
  });
}

/**
 * Processes PDF document data
 */
function processPdfField(pdfData, strapiUrl) {
  if (!pdfData) return null;

  let url = null;

  // Если это массив (consentAgreement)
  if (Array.isArray(pdfData)) {
    const firstPdf = pdfData[0];
    if (!firstPdf) return null;
    const pdfAttr = firstPdf.attributes || firstPdf;
    url = pdfAttr?.url;
  }
  // Если это объект с data (privacyPolicy)
  else if (pdfData.data) {
    const pdfAttr = pdfData.data.attributes || pdfData.data;
    url = pdfAttr?.url;
  }
  // Если это прямой объект
  else {
    url = pdfData.attributes?.url || pdfData.url;
  }

  if (!url) return null;

  // Если путь относительный, добавляем /api/ для проксирования
  if (url.startsWith("/uploads/")) {
    return `/api${url}`;
  }

  // Если это абсолютный URL Strapi, заменяем на проксированный путь
  if (url.startsWith(strapiUrl)) {
    const path = url.replace(strapiUrl, "").replace(/^\//, "");
    if (path.startsWith("uploads/")) {
      return `/api/${path}`;
    }
  }

  // Если уже абсолютный URL (не от Strapi), возвращаем как есть
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }

  // Fallback: добавляем strapiUrl
  return url.startsWith("/") ? `${strapiUrl}${url}` : `${strapiUrl}/${url}`;
}

/**
 * Processes location data
 */
function processLocation(locationData) {
  if (!locationData) return null;

  const locationAttributes =
    locationData.data?.attributes || locationData.attributes || locationData;
  if (!locationAttributes) return null;

  return {
    lat: Number(locationAttributes.lat) || 0,
    lng: Number(locationAttributes.lng) || 0,
  };
}

/**
 * Validates environment variables (ТОЛЬКО публичные)
 */
function validateEnv(env) {
  const envSchema = z.object({
    NEXT_PUBLIC_STRAPI_BASE_URL: z.string().min(1),
  });

  const validated = envSchema.safeParse(env);
  if (!validated.success) {
    throw new Error("Invalid environment variables");
  }
  return validated.data;
}

/**
 * Fetches raw restaurant data from Strapi (БЕЗ секретного токена)
 */
async function fetchRawData(slug, envData) {
  const { NEXT_PUBLIC_STRAPI_BASE_URL } = envData;

  if (!NEXT_PUBLIC_STRAPI_BASE_URL) {
    throw new Error("Missing environment variables");
  }

  const STRAPI_URL =
    process.env.NEXT_PUBLIC_STRAPI_URL || NEXT_PUBLIC_STRAPI_BASE_URL;

  const populateQuery = [
    "populate[image][fields]=url,formats,name,width,height",
    "populate[gallery][fields]=url,formats,name,width,height",
    "populate[menuItem][populate][image][fields]=url,formats,name,width,height",
    "populate[menuGallery][fields]=url,formats,name,width,height",
    "populate[scheduleItem][fields]=dayName,open,close",
    "populate[location][fields]=lat,lng",
    "populate[table][fields]=number,seats_min,seats_max,is_active",
    "populate[privacyPolicy][fields]=url,name",
    "populate[consentAgreement][fields]=url,name",
  ].join("&");

  const url = `${NEXT_PUBLIC_STRAPI_BASE_URL}/api/restaurants?filters[slug][$eq]=${encodeURIComponent(
    slug
  )}&${populateQuery}`;

  try {
    const response = await fetch(url, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      let errorMessage = `Strapi API error: ${response.status}`;
      try {
        const errorData = await response.text();
        errorMessage += ` - ${errorData}`;
      } catch (e) {
        // Ignore if we can't read error response
      }
      throw new Error(errorMessage);
    }

    const responseData = await response.json();

    if (!responseData.data || responseData.data.length === 0) {
      throw new Error("Restaurant not found");
    }

    return { data: responseData.data[0], STRAPI_URL };
  } catch (error) {
    throw error;
  }
}

/**
 * Processes related data for restaurant
 */
async function processRelatedData(baseRestaurant, strapiUrl) {
  const attributes = baseRestaurant.attributes || baseRestaurant;

  const [
    processedImage,
    processedGallery,
    processedMenuItems,
    processedMenuGallery,
    processedHallMap, // NEW
    rawTables, // NEW
    processedPrivacyPolicy,
    processedConsentAgreement,
  ] = await Promise.all([
    processImageData(attributes.image, strapiUrl),
    processGallery(attributes.gallery, strapiUrl),
    processMenuItems(attributes.menuItem, strapiUrl),
    processMenuGallery(attributes.menuGallery, strapiUrl),
    processImageData(attributes.hall_map, strapiUrl), // NEW: как image
    Promise.resolve(attributes.tables?.data || []), // NEW: raw tables
    Promise.resolve(processPdfField(attributes.privacyPolicy, strapiUrl)),
    Promise.resolve(processPdfField(attributes.consentAgreement, strapiUrl)),
  ]);

  const processedTables = rawTables
    .map((table) => {
      // NEW: маппинг
      const attrs = table.attributes || table;
      return {
        id: table.id,
        number: attrs.number || 0,
        seatsMin: attrs.seats_min || 1,
        seatsMax: attrs.seats_max || 6,
        locationMark: attrs.location_mark || "",
        type: attrs.type || "medium",
        isActive: attrs.is_active ?? true,
      };
    })
    .filter((t) => t.isActive); // Фильтр активных

  return {
    processedImage,
    processedGallery,
    processedMenuItems,
    processedMenuGallery,
    processedHallMap,
    processedTables,
    processedPrivacyPolicy,
    processedConsentAgreement,
  };
}

/**
 * Normalizes restaurant data (ДОБАВЛЯЕМ restaurantId для CRM)
 */
function normalizeRestaurantData(targetRestaurant, processedData) {
  const attributes = targetRestaurant.attributes || targetRestaurant;
  const {
    processedImage,
    processedGallery,
    processedMenuItems,
    processedMenuGallery,
  } = processedData;

  let locationData = null;
  if (attributes.location) {
    if (typeof attributes.location === "object") {
      locationData = {
        lat: Number(attributes.location.lat) || 55.7558,
        lng: Number(attributes.location.lng) || 37.6173,
      };
    }
  }

  return {
    id: targetRestaurant.id,
    documentId: targetRestaurant.documentId || "",
    // ДОБАВЛЯЕМ restaurantId для использования в CRM (берем из id Strapi)
    restaurantId: targetRestaurant.id,
    slug: attributes.slug || "",
    name: attributes.name || "",
    description: attributes.description || "",
    fullDescription: attributes.fullDescription || attributes.description || "",
    address: attributes.address || "",
    avgCheck: Number(attributes.avgCheck) || 0,
    kitchen: attributes.kitchen || "",
    metro: attributes.metro || "",
    phone: attributes.phone || "",
    max_guests_for_online: attributes.max_guests_for_online || "",
    features: attributes.features
      ? typeof attributes.features === "string"
        ? attributes.features.split(", ")
        : attributes.features
      : [],
    image: processedImage,
    gallery: processedGallery,
    menuItems: processedMenuItems,
    menuGallery: processedMenuGallery,
    scheduleItem: processSchedule(attributes.scheduleItem),
    location: locationData,
    hallMap: processedData.processedHallMap,
    tables: processedData.processedTables,
    privacyPolicy: processedData.processedPrivacyPolicy,
    consentAgreement: processedData.processedConsentAgreement,
  };
}

/**
 * Fetches and processes restaurant data
 */
async function fetchRestaurantData(slug) {
  try {
    const envData = validateEnv({
      NEXT_PUBLIC_STRAPI_BASE_URL: process.env.NEXT_PUBLIC_STRAPI_BASE_URL,
    });

    const { data: targetRestaurant, STRAPI_URL } = await fetchRawData(
      slug,
      envData
    );
    const processedData = await processRelatedData(
      targetRestaurant,
      STRAPI_URL
    );
    return normalizeRestaurantData(targetRestaurant, processedData);
  } catch (error) {
    throw error;
  }
}

/**
 * Generates metadata for the restaurant page
 */
export async function generateMetadata({ params }) {
  const { slug } = await params;
  if (!slug) return { title: "Restaurant not found" };

  if (metadataCache.has(slug)) return metadataCache.get(slug);

  try {
    const restaurant = await fetchRestaurantData(slug);
    const metadata = {
      title: `${restaurant.name} | Chain`,
      description: restaurant.description,
      openGraph: {
        title: restaurant.name,
        description: restaurant.description,
        images: restaurant.image?.url
          ? [restaurant.image.url]
          : ["/og-image.jpg"],
        type: "website",
        locale: "ru_RU",
      },
      alternates: {
        canonical: `/restaurant/${slug}`,
      },
    };

    metadataCache.set(slug, metadata);
    if (metadataCache.size > BLUR_CACHE_MAX_SIZE) {
      const oldestKey = metadataCache.keys().next().value;
      metadataCache.delete(oldestKey);
    }

    return metadata;
  } catch {
    return {
      title: "Restaurant | Chain",
      description: "Discover our restaurant",
    };
  }
}

/**
 * Restaurant page Server Component
 */
export default async function RestaurantPage({ params }) {
  const { slug } = await params;
  if (!slug) notFound();

  let restaurant;

  try {
    restaurant = await fetchRestaurantData(slug);
  } catch (error) {
    if (error.message.includes("not found") || error.message.includes("404")) {
      notFound();
    }
    return <ErrorFallback error={error} />;
  }

  return (
    <div className={styles.mainContainer}>
      <Suspense
        fallback={
          <div className={styles.loading}>
            <div className={styles.spinner} />
            Загрузка...
          </div>
        }
      >
        <ClientPage restaurant={restaurant} slug={slug} />
      </Suspense>
    </div>
  );
}

/**
 * Clears caches to prevent memory leaks
 */
export function clearCaches() {
  blurCache.clear();
  metadataCache.clear();
}
