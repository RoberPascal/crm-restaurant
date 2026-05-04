// app/ErrorFallback.jsx
"use client";

import { useRouter } from "next/navigation";
import styles from "./page.module.scss";

export default function ErrorFallback({ error }) {
  const router = useRouter();

  return (
    <div className={styles.errorBanner}>
      <div className={styles.errorContent}>
        <div className={styles.errorText}>
          {error.message || "Ошибка загрузки"}
        </div>
        <button className={styles.retryButton} onClick={() => router.refresh()}>
          Попробовать снова
        </button>
      </div>
    </div>
  );
}
