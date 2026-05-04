// utils/api.js
const API_BASE = process.env.NEXT_PUBLIC_CRM_API_URL;
const IS_DEV = process.env.NODE_ENV === "development";

// ОПТИМИЗАЦИЯ: Логирование только в development режиме
const debugLog = IS_DEV ? console.log.bind(console) : () => {};

if (!API_BASE) {
  if (typeof window !== "undefined") {
    console.error("NEXT_PUBLIC_CRM_API_URL не задан!");
  }
}

class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const apiFetch = async (url, options = {}) => {
  const headers = {
    ...options.headers,
    "X-WebApp-Source": "webapp",
    "Content-Type": "application/json",
  };

  // 🔑 Передаём initData из Telegram, если доступен
  if (typeof window !== "undefined" && window.Telegram?.WebApp?.initData) {
    headers["X-Telegram-Init-Data"] = window.Telegram.WebApp.initData;
  }

  const config = {
    ...options,
    headers,
    credentials: "include", // для куки (если в будущем добавишь)
  };

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    const response = await fetch(`${API_BASE}${url}`, {
      ...config,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    debugLog(`API Request: ${url}`, { status: response.status });

    if (!response.ok) {
      let errorDetail = `HTTP ${response.status}`;

      try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorDetail;
      } catch {
        // Ignore JSON parse errors
      }

      throw new ApiError(errorDetail, response.status, "HTTP_ERROR");
    }

    // Для 204 No Content не парсим JSON
    if (response.status === 204) {
      return null;
    }

    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }

    // Retry на сетевые ошибки (только GET-подобные запросы)
    const method = (options.method || "GET").toUpperCase();
    const isGetLike = ["GET", "HEAD", "OPTIONS"].includes(method);
    if (isGetLike) {
      debugLog("Retrying after network error...");
      await new Promise((r) => setTimeout(r, 1000));
      try {
        const controller2 = new AbortController();
        const timeoutId2 = setTimeout(() => controller2.abort(), 30000);
        const retryResp = await fetch(`${API_BASE}${url}`, {
          ...config,
          signal: controller2.signal,
        });
        clearTimeout(timeoutId2);
        if (retryResp.ok) {
          if (retryResp.status === 204) return null;
          return await retryResp.json();
        }
      } catch {
        // Повтор не удался
      }
    }

    throw new ApiError(error.message || "Network error", 0, "NETWORK_ERROR");
  }
};

export const api = {
  get: (url, options = {}) => apiFetch(url, { ...options, method: "GET" }),
  post: (url, data, options = {}) =>
    apiFetch(url, { ...options, method: "POST", body: JSON.stringify(data) }),
  patch: (url, data, options = {}) =>
    apiFetch(url, { ...options, method: "PATCH", body: JSON.stringify(data) }),
  delete: (url, options = {}) =>
    apiFetch(url, { ...options, method: "DELETE" }),
};
