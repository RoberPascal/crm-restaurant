"use client";

import styles from "./RestaurantPage.module.scss";

/**
 * Error fallback Client Component
 * @param {{ error: Error }} props
 * @returns {JSX.Element}
 */
export default function ErrorFallback({ error }) {
  return (
    <div className={styles.errorPage}>
      <h2>Something went wrong</h2>
      <p>{error.message || "Failed to load restaurant page"}</p>
      <button
        className={styles.backButton}
        onClick={() => window.history.back()}
      >
        Back
      </button>
    </div>
  );
}
