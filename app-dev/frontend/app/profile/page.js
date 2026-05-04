// app/profile/page.js
"use client";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Header } from "@/components/Header/Header";
import { api } from "@/utils/api";
import styles from "./page.module.scss";

export default function Profile() {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const data = await api.get("/api/v1/public/me");
        setUser(data);
      } catch (err) {
        console.error("Failed to fetch profile:", err);
        setError(err.message || "Не удалось загрузить профиль");
      } finally {
        setIsLoading(false);
      }
    };

    fetchProfile();
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setUser((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);
    setSuccessMessage("");

    try {
      const updateData = {
        first_name: user.first_name || null,
        last_name: user.last_name || null,
        phone: user.phone || null,
        birth_date: user.birth_date || null,
        allergies: user.allergies || null,
      };

      const updated = await api.patch("/api/v1/public/me", updateData);
      setUser(updated);
      setSuccessMessage("✅ Данные успешно сохранены");

      // Clear success message after 3 seconds
      setTimeout(() => {
        setSuccessMessage("");
      }, 3000);
    } catch (err) {
      console.error("Failed to update profile:", err);
      setError(err.message || "Не удалось сохранить изменения");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) return <div className={styles.loading}>Загрузка...</div>;

  if (!user) {
    return (
      <div className={styles.container}>
        <Header showBackButton={true} />
        <div className={styles.error}>
          {error || "Не удалось загрузить профиль"}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <Header showBackButton={true} />
      <motion.main
        className={styles.main}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <h1>Профиль</h1>
        {error && <div className={styles.error}>{error}</div>}
        {successMessage && (
          <div className={styles.success}>{successMessage}</div>
        )}
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label>Имя</label>
            <input
              name="first_name"
              value={user.first_name || ""}
              onChange={handleChange}
              placeholder="Введите ваше имя"
            />
          </div>
          <div className={styles.field}>
            <label>Фамилия</label>
            <input
              name="last_name"
              value={user.last_name || ""}
              onChange={handleChange}
              placeholder="Введите вашу фамилию"
            />
          </div>
          <div className={styles.field}>
            <label>Telegram</label>
            <input
              value={user.username ? `@${user.username}` : "—"}
              readOnly
              className={styles.readonly}
            />
          </div>
          <div className={styles.field}>
            <label>Телефон</label>
            <input
              name="phone"
              value={user.phone || ""}
              onChange={handleChange}
              placeholder="+7 (___) ___-__-__"
            />
          </div>
          <div className={styles.field}>
            <label>Дата рождения</label>
            <input
              name="birth_date"
              type="date"
              value={user.birth_date || ""}
              onChange={handleChange}
            />
          </div>
          <div className={styles.field}>
            <label>Аллергия</label>
            <textarea
              name="allergies"
              value={user.allergies || ""}
              onChange={handleChange}
              placeholder="Например: арахис, молоко..."
              rows={3}
            />
          </div>
          <button
            type="submit"
            disabled={isSaving}
            className={styles.saveButton}
          >
            {isSaving ? "Сохранение..." : "Сохранить"}
          </button>
        </form>
      </motion.main>
    </div>
  );
}
