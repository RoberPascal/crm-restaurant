// utils/api.js
const API_BASE = process.env.NEXT_PUBLIC_API_URL;
const IS_DEV = process.env.NODE_ENV === "development";

// ОПТИМИЗАЦИЯ: Логирование только в development режиме
const debugLog = IS_DEV ? console.log.bind(console) : () => {};
const debugWarn = IS_DEV ? console.warn.bind(console) : () => {};

if (!API_BASE) {
  throw new Error("NEXT_PUBLIC_API_URL не задан! Пересобери фронтенд.");
}

class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const getCsrfTokenFromCookie = () => {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/csrf_token=([^;]+)/);
  if (!match) return null;

  try {
    return decodeURIComponent(match[1]);
  } catch (e) {
    return match[1];
  }
};

export const getAccessTokenFromCookie = () => {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/access_token=([^;]+)/);
  if (!match) return null;

  const token = decodeURIComponent(match[1]);
  return token.startsWith("Bearer ") ? token.slice(7) : token;
};

export const isTokenValid = (token) => {
  if (!token) return false;

  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return Date.now() < payload.exp * 1000;
  } catch {
    return false;
  }
};

// Глобальная блокировка для предотвращения множественных обновлений CSRF
let csrfRenewalInProgress = false;
let csrfRenewalPromise = null;

const renewCsrf = async () => {
  // Если уже обновляем CSRF, ждем завершения
  if (csrfRenewalInProgress) {
    return await csrfRenewalPromise;
  }

  csrfRenewalInProgress = true;
  csrfRenewalPromise = (async () => {
    try {
      debugLog("Renewing CSRF token...");
      const resp = await fetch(`${API_BASE}/api/v1/admin/auth/renew-csrf`, {
        method: "GET",
        credentials: "include",
        headers: {
          "X-WebApp-Source": "*",
          "Cache-Control": "no-cache",
        },
      });

      if (!resp.ok) {
        throw new Error(`CSRF renewal failed: ${resp.status}`);
      }

      debugLog("CSRF token renewed successfully");
      return true;
    } catch (error) {
      console.error("CSRF renewal error:", error);
      return false;
    } finally {
      csrfRenewalInProgress = false;
      csrfRenewalPromise = null;
    }
  })();

  return await csrfRenewalPromise;
};

export const parseApiResponse = async (response) => {
  const contentType = response.headers.get("content-type");
  const contentLength = response.headers.get("content-length");

  if (contentLength === "0" || !contentType) {
    return { success: true };
  }

  if (contentType && contentType.includes("application/json")) {
    try {
      const text = await response.text();
      return text ? JSON.parse(text) : {};
    } catch (e) {
      debugWarn("Failed to parse JSON response:", e);
      return {};
    }
  }

  const text = await response.text();
  return text || { success: true };
};

// Функция для принудительного обновления CSRF токена
export const forceRenewCsrf = async () => {
  return await renewCsrf();
};

// Базовые заголовки для ВСЕХ запросов
const getBaseHeaders = () => ({
  "X-WebApp-Source": "*",
  // User-Agent нельзя устанавливать из браузера - это forbidden header
});

// Специальная функция для получения CSRF токена
export const getCsrfToken = async () => {
  try {
    debugLog("Fetching CSRF token...");

    const headers = {
      "X-WebApp-Source": "*",
      Accept: "application/json",
      "Cache-Control": "no-cache",
    };

    // Добавляем Origin для CORS
    if (typeof window !== "undefined" && window.location.origin) {
      headers["Origin"] = window.location.origin;
    }

    const response = await fetch(`${API_BASE}/api/v1/admin/auth/csrf`, {
      method: "GET",
      credentials: "include",
      headers: headers,
    });

    debugLog("CSRF fetch response:", response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("CSRF fetch failed:", errorText);
      throw new ApiError(
        `CSRF fetch failed: ${response.status}`,
        response.status,
      );
    }

    const data = await response.json();

    // Проверяем, что токен установлен в cookie
    await new Promise((resolve) => setTimeout(resolve, 100));
    const cookieToken = getCsrfTokenFromCookie();
    debugLog("CSRF token in cookie:", !!cookieToken);

    return data;
  } catch (error) {
    console.error("CSRF token fetch error:", error);
    throw error;
  }
};

export const apiFetch = async (url, options = {}) => {
  const method = options.method?.toUpperCase() || "GET";
  const isGetLike = ["GET", "HEAD", "OPTIONS"].includes(method);

  // Получаем текущий CSRF токен
  let csrfToken = getCsrfTokenFromCookie();

  // Базовые заголовки для всех запросов
  const baseHeaders = getBaseHeaders();

  const headers = {
    ...baseHeaders,
    ...options.headers,
  };

  // Для CSRF endpoint добавляем специальные заголовки
  if (url.includes("/auth/csrf")) {
    headers["Accept"] = "application/json";
    headers["Cache-Control"] = "no-cache";
  }

  if (!isGetLike || options.body) {
    headers["Content-Type"] =
      options.headers?.["Content-Type"] || "application/json";
  }

  // Добавляем CSRF токен для не-GET запросов
  if (csrfToken && !isGetLike) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const config = {
    ...options,
    headers,
    credentials: "include",
  };

  const tryRequest = async (attempt = 0) => {
    debugLog(`API Request (attempt ${attempt}): ${method} ${url}`);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(`${API_BASE}${url}`, {
        ...config,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      debugLog(`API Response: ${method} ${url} -> ${response.status}`);

      // Обработка 401 - неавторизован
      if (response.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.clear();
          window.location.href = "/login";
        }
        throw new ApiError("Authentication required", 401, "UNAUTHENTICATED");
      }

      // Обработка 403 - запрещено
      if (response.status === 403) {
        let detail = "";
        let isCsrfError = false;

        try {
          const data = await parseApiResponse(response.clone());
          detail = data?.detail || data?.message || "";
          isCsrfError =
            /CSRF token/i.test(detail) || /csrf/i.test(detail.toLowerCase());
          debugLog("403 Error details:", { detail, isCsrfError });
        } catch (e) {
          debugWarn("Failed to parse 403 response:", e);
        }

        // Если это CSRF ошибка и мы еще не пытались обновить токен
        if (isCsrfError && attempt === 0) {
          debugLog("CSRF error detected, renewing token...");
          try {
            const renewed = await renewCsrf();
            if (renewed) {
              // Даем время для установки cookie
              await new Promise((resolve) => setTimeout(resolve, 100));
              // Обновляем CSRF токен в заголовках и пробуем снова
              const newCsrfToken = getCsrfTokenFromCookie();
              if (newCsrfToken) {
                config.headers["X-CSRF-Token"] = newCsrfToken;
                debugLog("Retrying request with renewed CSRF token");
                return tryRequest(1);
              } else {
                debugWarn("CSRF token not found in cookie after renewal");
              }
            }
          } catch (renewError) {
            console.error("Failed to renew CSRF token:", renewError);
          }
        }

        throw new ApiError(detail || "Access denied", 403, "FORBIDDEN");
      }

      // Обработка 400 - плохой запрос (ИСПРАВЛЕНО: убран бессмысленный retry на клиентские ошибки)
      if (response.status === 400) {
        let detail = "";
        try {
          const data = await parseApiResponse(response.clone());
          detail = data?.detail || data?.message || "";
          debugLog("400 Error details:", { detail });
        } catch (e) {
          debugWarn("Failed to parse 400 response:", e);
        }

        throw new ApiError(detail || "Bad request", 400, "BAD_REQUEST");
      }

      // Обработка 429 - слишком много запросов
      if (response.status === 429) {
        throw new ApiError("Too many requests", 429, "RATE_LIMITED");
      }

      // Обработка других ошибок
      if (!response.ok) {
        const errorData = await parseApiResponse(response.clone());
        throw new ApiError(
          errorData.detail || errorData.message || `HTTP ${response.status}`,
          response.status,
          errorData.code,
        );
      }

      return await parseApiResponse(response);
    } finally {
      clearTimeout(timeoutId);
    }
  };

  try {
    return await tryRequest(0);
  } catch (error) {
    // Retry на сетевые ошибки и 5xx (не на клиентские 4xx)
    const isRetryable =
      error.code === "NETWORK_ERROR" ||
      error.name === "AbortError" ||
      (error instanceof ApiError && error.status >= 500);

    if (isRetryable && isGetLike) {
      debugLog("Retrying after network/server error...");
      await new Promise((r) => setTimeout(r, 1000));
      try {
        return await tryRequest(1);
      } catch (retryError) {
        if (retryError instanceof ApiError) throw retryError;
        throw new ApiError(
          retryError.message || "Network error",
          0,
          "NETWORK_ERROR",
        );
      }
    }

    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(error.message || "Network error", 0, "NETWORK_ERROR");
  }
};

export const apiForm = async (url, data, options = {}) => {
  return apiFetch(url, {
    ...options,
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      ...options.headers,
    },
    body: new URLSearchParams(data),
  });
};

export const api = {
  get: (url, options = {}) => apiFetch(url, { ...options, method: "GET" }),
  post: (url, data, options = {}) =>
    apiFetch(url, { ...options, method: "POST", body: JSON.stringify(data) }),
  postForm: (url, data, options = {}) => apiForm(url, data, options),
  put: (url, data, options = {}) =>
    apiFetch(url, { ...options, method: "PUT", body: JSON.stringify(data) }),
  patch: (url, data, options = {}) =>
    apiFetch(url, { ...options, method: "PATCH", body: JSON.stringify(data) }),
  delete: (url, options = {}) =>
    apiFetch(url, { ...options, method: "DELETE" }),
  renewCsrf: () => renewCsrf(),
};
