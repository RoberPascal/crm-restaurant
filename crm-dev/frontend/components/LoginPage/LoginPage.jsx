// app/components/LoginPage/LoginPage.jsx
"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  apiForm,
  getCsrfTokenFromCookie,
  getCsrfToken,
} from "@/utils/api";
import styles from "./LoginPage.module.scss";

const EyeIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    aria-hidden="true"
  >
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const EyeOffIcon = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    aria-hidden="true"
  >
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
);

const AlertIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);

const Spinner = () => (
  <svg
    className={styles.spinner}
    width="16"
    height="16"
    viewBox="0 0 24 24"
    aria-hidden="true"
  >
    <circle
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      strokeWidth="2"
      fill="none"
      strokeDasharray="15"
    />
  </svg>
);

const sanitizeInput = (input) => {
  return input.trim().replace(/[<>"'`]/g, "");
};

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [attempts, setAttempts] = useState(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("login_attempts");
      return saved ? parseInt(saved, 10) || 0 : 0;
    }
    return 0;
  });
  const [locked, setLocked] = useState(false);
  const [lockTime, setLockTime] = useState(0);

  const usernameRef = useRef(null);
  const router = useRouter();

  useEffect(() => {
    usernameRef.current?.focus();

    const savedLock = localStorage.getItem("login_lock");
    if (savedLock) {
      try {
        const lockData = JSON.parse(savedLock);
        if (lockData.expires > Date.now()) {
          setLocked(true);
          setLockTime(Math.ceil((lockData.expires - Date.now()) / 1000));
        } else {
          localStorage.removeItem("login_lock");
        }
      } catch {
        localStorage.removeItem("login_lock");
      }
    }
  }, []);

  useEffect(() => {
    if (!locked) return;

    const timer = setInterval(() => {
      setLockTime((prev) => {
        if (prev <= 1) {
          setLocked(false);
          localStorage.removeItem("login_lock");
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [locked]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (locked) {
      setError(`Слишком много попыток. Подождите ${lockTime} секунд.`);
      return;
    }

    setLoading(true);
    setError("");

    const trimmedUsername = sanitizeInput(username);
    const trimmedPassword = password.trim();

    if (!trimmedUsername || !trimmedPassword) {
      setError("Заполните логин и пароль");
      setLoading(false);
      return;
    }

    try {
      // Шаг 1: Получаем CSRF токен используя специальную функцию
      let csrfData;
      try {
        csrfData = await getCsrfToken();
      } catch (csrfError) {
        throw new Error(
          "Не удалось получить CSRF токен. Проверьте подключение к серверу.",
        );
      }

      if (!csrfData || !csrfData.csrf_token) {
        throw new Error("Не удалось получить CSRF токен");
      }

      const csrfToken = csrfData.csrf_token;

      // Проверяем, что токен установлен в cookie
      const cookieToken = getCsrfTokenFromCookie();

      // Шаг 2: Выполняем логин

      // Используем apiForm для отправки формы
      const loginResponse = await apiForm("/api/v1/admin/auth/login", {
        username: trimmedUsername,
        password: trimmedPassword,
        grant_type: "password",
      });

      // Проверяем успешность логина
      if (loginResponse && loginResponse.access_token) {
        setAttempts(0);
        localStorage.removeItem("login_attempts");
        localStorage.removeItem("login_lock");

        // Даем время для установки cookies
        await new Promise((resolve) => setTimeout(resolve, 500));

        // Проверяем авторизацию
        try {
          const meResponse = await api.get("/api/v1/admin/auth/me");
          // Редирект на главную
          window.location.href = "/";
        } catch (meError) {
          throw new Error("Ошибка проверки авторизации");
        }
      } else {
        throw new Error(loginResponse?.detail || "Неверный логин или пароль");
      }
    } catch (err) {
      const newAttempts = attempts + 1;
      setAttempts(newAttempts);
      localStorage.setItem("login_attempts", String(newAttempts));

      if (newAttempts >= 5) {
        const lockDuration = 30 * 1000;
        const expires = Date.now() + lockDuration;
        localStorage.setItem("login_lock", JSON.stringify({ expires }));
        setLocked(true);
        setLockTime(30);
        setError("Слишком много попыток. Подождите 30 секунд.");
      } else {
        setError(err.message || "Неверный логин или пароль");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.loginWrapper}>
      <div className={styles.loginCard}>
        <div className={styles.logo}>
          <h1 className={styles.title}>CRM Рестораны</h1>
          <p className={styles.subtitle}>Система управления бронированиями</p>
        </div>

        <form onSubmit={handleSubmit} noValidate className={styles.form}>
          <div className={styles.inputGroup}>
            <label htmlFor="login" className={styles.label}>
              Логин
            </label>
            <input
              ref={usernameRef}
              type="text"
              id="login"
              className={styles.input}
              placeholder="Введите логин"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading || locked}
              autoComplete="username"
              aria-required="true"
              aria-invalid={error ? "true" : "false"}
            />
          </div>

          <div className={styles.inputGroup}>
            <label htmlFor="password" className={styles.label}>
              Пароль
            </label>
            <div className={styles.inputWrapper}>
              <input
                type={showPassword ? "text" : "password"}
                id="password"
                className={styles.input}
                placeholder="Введите пароль"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading || locked}
                autoComplete="current-password"
                aria-required="true"
                aria-invalid={error ? "true" : "false"}
              />
              <button
                type="button"
                className={styles.passwordToggle}
                onClick={() => setShowPassword(!showPassword)}
                disabled={loading || locked}
                aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
          </div>

          {error && (
            <div className={styles.error} role="alert" aria-live="polite">
              <AlertIcon />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            className={styles.button}
            disabled={loading || locked}
            aria-busy={loading}
          >
            {loading ? (
              <>
                <Spinner />
                <span>Вход...</span>
              </>
            ) : locked ? (
              `Заблокировано (${lockTime}с)`
            ) : (
              "Войти"
            )}
          </button>
        </form>

        <div className={styles.footer}>
          <p>Нужна помощь? Обратитесь к администратору</p>
        </div>
      </div>
    </div>
  );
}
