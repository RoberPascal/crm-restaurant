// app/employees/page.jsx
"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { DashboardProvider } from "@/context/DashboardContext";
import styles from "./EmployeesPage.module.scss";
import { useDashboard } from "@/context/DashboardContext";
import { api } from "@/utils/api";
import Header from "@/components/Header/Header";

// Иконки
const Icons = {
  Back: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M15 18L9 12L15 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Plus: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 5V19M5 12H19"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Edit: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M11 4H4C3.46957 4 2.96086 4.21071 2.58579 4.58579C2.21071 4.96086 2 5.46957 2 6V20C2 20.5304 2.21071 21.0391 2.58579 21.4142C2.96086 21.7893 3.46957 22 4 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V13"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M18.5 2.5C18.8978 2.10217 19.4374 1.87868 20 1.87868C20.5626 1.87868 21.1022 2.10217 21.5 2.5C21.8978 2.89782 22.1213 3.43739 22.1213 4C22.1213 4.56261 21.8978 5.10217 21.5 5.5L12 15L8 16L9 12L18.5 2.5Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Delete: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M3 6H5H21"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8 6V4C8 3.46957 8.21071 2.96086 8.58579 2.58579C8.96086 2.21071 9.46957 2 10 2H14C14.5304 2 15.0391 2.21071 15.4142 2.58579C15.7893 2.96086 16 3.46957 16 4V6M19 6V20C19 20.5304 18.7893 21.0391 18.4142 21.4142C18.0391 21.7893 17.5304 22 17 22H7C6.46957 22 5.96086 21.7893 5.58579 21.4142C5.21071 21.0391 5 20.5304 5 20V6H19Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10 11V17"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M14 11V17"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Key: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M21 2L19 4M11.39 11.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.778-7.778zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Close: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
      <path
        d="M18 6L6 18M6 6l12 12"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Eye: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx="12"
        cy="12"
        r="3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  EyeOff: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <line
        x1="1"
        y1="1"
        x2="23"
        y2="23"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Copy: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <rect
        x="9"
        y="9"
        width="13"
        height="13"
        rx="2"
        ry="2"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Refresh: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path
        d="M23 4v6h-6M1 20v-6h6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
  Alert: () => (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  ),
};

const Spinner = () => (
  <svg className={styles.spinner} width="16" height="16" viewBox="0 0 24 24">
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

// Константы
const ROLE_DISPLAY_NAMES = {
  admin: "Администратор",
  operator: "Оператор",
  waiter: "Сотрудник зала",
};

const MODAL_TYPES = {
  EMPLOYEE: "employee",
  CHANGE_PASSWORD: "changePassword",
  DELETE_CONFIRM: "deleteConfirm",
  PASSWORD_DISPLAY: "passwordDisplay",
};

// Вспомогательные функции
const getRoleDisplayName = (role) => ROLE_DISPLAY_NAMES[role] || role;

const getRestaurantNames = (restaurantsList) => {
  if (!restaurantsList?.length) return "Нет доступа";
  if (restaurantsList.length > 2) return `${restaurantsList.length} заведений`;
  return restaurantsList.map((r) => r.name).join(", ");
};

// Компоненты модальных окон
const PasswordDisplayModal = ({ isOpen, onClose, username, password }) => {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy password:", error);
    }
  };

  if (!isOpen) return null;

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Новый пароль создан</h3>
          <button className={styles.closeButton} onClick={onClose}>
            <Icons.Close />
          </button>
        </div>

        <div className={styles.passwordDisplay}>
          <div className={styles.passwordInfo}>
            <p>
              <strong>Логин:</strong> {username}
            </p>
            <p>
              <strong>Пароль:</strong>
            </p>
          </div>

          <div className={styles.passwordValue}>
            <code className={styles.passwordText}>{password}</code>
            <button
              className={styles.copyButton}
              onClick={copyToClipboard}
              title="Скопировать пароль"
            >
              <Icons.Copy />
            </button>
          </div>

          {copied && (
            <div className={styles.copiedMessage}>
              Пароль скопирован в буфер обмена!
            </div>
          )}

          <div className={styles.passwordHint}>
            ⚠️ Сохраните этот пароль! Он больше не будет показан.
          </div>
        </div>

        <div className={styles.modalActions}>
          <button className={styles.submitButton} onClick={onClose}>
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};

const EmployeeModal = ({
  isOpen,
  onClose,
  onSubmit,
  editingUser,
  availableRestaurants,
  loading,
}) => {
  const [formData, setFormData] = useState({
    username: "",
    role: "operator",
    restaurant_ids: [],
  });
  const [error, setError] = useState("");

  useEffect(() => {
    if (editingUser) {
      setFormData({
        username: editingUser.username,
        role: editingUser.role,
        restaurant_ids: editingUser.restaurants?.map((r) => r.id) || [],
      });
    } else {
      setFormData({ username: "", role: "operator", restaurant_ids: [] });
    }
    setError("");
  }, [editingUser, isOpen]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleRestaurantToggle = (restaurantId) => {
    setFormData((prev) => ({
      ...prev,
      restaurant_ids: prev.restaurant_ids.includes(restaurantId)
        ? prev.restaurant_ids.filter((id) => id !== restaurantId)
        : [...prev.restaurant_ids, restaurantId],
    }));
  };

  const handleSelectAllRestaurants = () => {
    const allIds = availableRestaurants.map((r) => r.id);
    setFormData((prev) => ({ ...prev, restaurant_ids: allIds }));
  };

  const handleClearRestaurants = () => {
    setFormData((prev) => ({ ...prev, restaurant_ids: [] }));
  };

  const validateForm = () => {
    if (!formData.username.trim()) {
      setError("Логин обязателен");
      return false;
    }
    if (formData.username.length < 3) {
      setError("Логин должен содержать минимум 3 символа");
      return false;
    }
    if (formData.restaurant_ids.length === 0) {
      setError("Выберите хотя бы одно заведение");
      return false;
    }
    return true;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setError("");
    if (!validateForm()) return;
    onSubmit(formData);
  };

  const handleClose = () => {
    setFormData({ username: "", role: "operator", restaurant_ids: [] });
    setError("");
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>
            {editingUser ? "Редактирование сотрудника" : "Новый сотрудник"}
          </h3>
          <button className={styles.closeButton} onClick={handleClose}>
            <Icons.Close />
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.modalForm}>
          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label htmlFor="username" className={styles.label}>
                Логин *
              </label>
              <input
                type="text"
                id="username"
                name="username"
                className={styles.input}
                value={formData.username}
                onChange={handleInputChange}
                placeholder="Введите логин"
                disabled={loading}
                required
              />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="role" className={styles.label}>
                Роль *
              </label>
              <select
                id="role"
                name="role"
                className={styles.select}
                value={formData.role}
                onChange={handleInputChange}
                disabled={loading}
              >
                <option value="waiter">Сотрудник зала</option>
                <option value="operator">Оператор</option>
                <option value="admin">Администратор</option>
              </select>
            </div>
          </div>

          {!editingUser && (
            <div className={styles.passwordNote}>
              <Icons.Alert />
              <span>
                Пароль будет автоматически сгенерирован на сервере и показан
                после создания
              </span>
            </div>
          )}

          <div className={styles.formGroup}>
            <div className={styles.restaurantHeader}>
              <label className={styles.label}>Доступ к заведениям *</label>
              <div className={styles.restaurantActions}>
                <button
                  type="button"
                  className={styles.actionButton}
                  onClick={handleSelectAllRestaurants}
                >
                  Все
                </button>
                <button
                  type="button"
                  className={styles.actionButton}
                  onClick={handleClearRestaurants}
                >
                  Очистить
                </button>
              </div>
            </div>

            {availableRestaurants.length === 0 ? (
              <div className={styles.noRestaurants}>
                <p>Нет доступных ресторанов</p>
              </div>
            ) : (
              <div className={styles.restaurantList}>
                {availableRestaurants.map((restaurant) => (
                  <label key={restaurant.id} className={styles.restaurantItem}>
                    <input
                      type="checkbox"
                      checked={formData.restaurant_ids.includes(restaurant.id)}
                      onChange={() => handleRestaurantToggle(restaurant.id)}
                      disabled={loading}
                      className={styles.checkbox}
                    />
                    <span className={styles.restaurantName}>
                      {restaurant.name}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className={styles.alertError}>
              <Icons.Alert />
              <span>{error}</span>
            </div>
          )}

          <div className={styles.modalActions}>
            <button
              type="button"
              className={styles.cancelButton}
              onClick={handleClose}
              disabled={loading}
            >
              Отмена
            </button>
            <button
              type="submit"
              className={styles.submitButton}
              disabled={loading || availableRestaurants.length === 0}
            >
              {loading ? (
                <>
                  <Spinner />
                  <span>Сохранение...</span>
                </>
              ) : editingUser ? (
                "Сохранить"
              ) : (
                "Создать"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const ChangePasswordModal = ({ isOpen, onClose, onSubmit, loading }) => {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError("");

    if (password.length < 6) {
      setError("Пароль должен содержать минимум 6 символов");
      return;
    }

    if (password !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }

    onSubmit(password);
  };

  const handleClose = () => {
    setPassword("");
    setConfirmPassword("");
    setError("");
    setShowPassword(false);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Смена пароля</h3>
          <button className={styles.closeButton} onClick={handleClose}>
            <Icons.Close />
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.modalForm}>
          <div className={styles.formGroup}>
            <label htmlFor="newPassword" className={styles.label}>
              Новый пароль *
            </label>
            <div className={styles.passwordInputWrapper}>
              <input
                type={showPassword ? "text" : "password"}
                id="newPassword"
                className={styles.input}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Введите новый пароль"
                required
                minLength={6}
              />
              <button
                type="button"
                className={styles.passwordToggle}
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <Icons.EyeOff /> : <Icons.Eye />}
              </button>
            </div>
          </div>

          <div className={styles.formGroup}>
            <label htmlFor="confirmPassword" className={styles.label}>
              Подтвердите пароль *
            </label>
            <div className={styles.passwordInputWrapper}>
              <input
                type={showPassword ? "text" : "password"}
                id="confirmPassword"
                className={styles.input}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Повторите пароль"
                required
                minLength={6}
              />
              <button
                type="button"
                className={styles.passwordToggle}
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <Icons.EyeOff /> : <Icons.Eye />}
              </button>
            </div>
          </div>

          {error && (
            <div className={styles.alertError}>
              <Icons.Alert />
              <span>{error}</span>
            </div>
          )}

          <div className={styles.modalActions}>
            <button
              type="button"
              className={styles.cancelButton}
              onClick={handleClose}
              disabled={loading}
            >
              Отмена
            </button>
            <button
              type="submit"
              className={styles.submitButton}
              disabled={loading}
            >
              {loading ? (
                <>
                  <Spinner />
                  <span>Сохранение...</span>
                </>
              ) : (
                "Сохранить"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const DeleteConfirmModal = ({
  isOpen,
  onClose,
  onConfirm,
  loading,
  userName,
}) => {
  if (!isOpen) return null;

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>Подтверждение удаления</h3>
          <button className={styles.closeButton} onClick={onClose}>
            <Icons.Close />
          </button>
        </div>

        <div className={styles.modalContent}>
          <p>
            Вы уверены, что хотите удалить сотрудника{" "}
            <strong>{userName}</strong>?
          </p>
          <p className={styles.warningText}>Это действие нельзя отменить.</p>
        </div>

        <div className={styles.modalActions}>
          <button
            type="button"
            className={styles.cancelButton}
            onClick={onClose}
            disabled={loading}
          >
            Отмена
          </button>
          <button
            type="button"
            className={styles.deleteButton}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? (
              <>
                <Spinner />
                <span>Удаление...</span>
              </>
            ) : (
              "Удалить"
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

// Основной компонент
const EmployeesContent = () => {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Берем данные из контекста
  const {
    user: currentUser,
    restaurants: userRestaurants,
    isAdmin,
  } = useDashboard();

  const router = useRouter();
  const authCheckRef = useRef(false);

  const [modals, setModals] = useState({
    employee: { isOpen: false, editingUser: null, loading: false },
    changePassword: { isOpen: false, userId: null, loading: false },
    deleteConfirm: {
      isOpen: false,
      userId: null,
      userName: "",
      loading: false,
    },
    passwordDisplay: { isOpen: false, username: "", password: "" },
  });

  // Получаем список ресторанов из контекста
  const availableRestaurants = isAdmin
    ? userRestaurants
    : userRestaurants || [];

  // Загрузка данных
  const loadUsers = async () => {
    try {
      const data = await api.get("/api/v1/admin/users");
      setUsers(data);
    } catch (error) {
      setError("Ошибка загрузки списка сотрудников");
    }
  };

  const checkAuthAndLoadData = async () => {
    try {
      await api.get("/api/v1/admin/auth/me");
      await loadUsers(); // Только пользователей, рестораны уже в контексте
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        router.push("/login");
      } else {
        setError("Ошибка соединения с сервером");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (authCheckRef.current) return;
    authCheckRef.current = true;
    checkAuthAndLoadData();
  }, []);

  // Управление уведомлениями
  const showSuccess = (message) => {
    setSuccess(message);
    setTimeout(() => setSuccess(""), 3000);
  };

  const clearError = () => setError("");

  // Обработчики действий
  const handleCreateUser = async (formData) => {
    setModals((prev) => ({
      ...prev,
      employee: { ...prev.employee, loading: true },
    }));

    try {
      const data = await api.post("/api/v1/admin/users", formData);

      setModals((prev) => ({
        ...prev,
        employee: { isOpen: false, editingUser: null, loading: false },
        passwordDisplay: {
          isOpen: true,
          username: data.username,
          password: data.password,
        },
      }));

      showSuccess(`Сотрудник ${data.username} создан!`);
      await loadUsers();
    } catch (error) {
      setError(error.message || "Ошибка при создании пользователя");
    } finally {
      setModals((prev) => ({
        ...prev,
        employee: { ...prev.employee, loading: false },
      }));
    }
  };

  const handleUpdateUser = async (formData) => {
    setModals((prev) => ({
      ...prev,
      employee: { ...prev.employee, loading: true },
    }));

    try {
      await api.put(
        `/api/v1/admin/users/${modals.employee.editingUser.id}`,
        formData,
      );

      setModals((prev) => ({
        ...prev,
        employee: { isOpen: false, editingUser: null, loading: false },
      }));

      showSuccess("Данные сотрудника обновлены");
      await loadUsers();
    } catch (error) {
      setError(error.message || "Ошибка при обновлении пользователя");
    } finally {
      setModals((prev) => ({
        ...prev,
        employee: { ...prev.employee, loading: false },
      }));
    }
  };

  const handleEmployeeSubmit = (formData) => {
    if (modals.employee.editingUser) {
      handleUpdateUser(formData);
    } else {
      handleCreateUser(formData);
    }
  };

  const handleResetPassword = async (userId, username) => {
    try {
      const data = await api.post(
        `/api/v1/admin/users/${userId}/reset-password`,
      );

      setModals((prev) => ({
        ...prev,
        passwordDisplay: {
          isOpen: true,
          username,
          password: data.new_password,
        },
      }));

      showSuccess("Пароль успешно сброшен");
    } catch (error) {
      setError(error.message || "Ошибка при сбросе пароля");
    }
  };

  const handleChangePassword = async (newPassword) => {
    setModals((prev) => ({
      ...prev,
      changePassword: { ...prev.changePassword, loading: true },
    }));

    try {
      await api.patch(
        `/api/v1/admin/users/${modals.changePassword.userId}/change-password`,
        {
          new_password: newPassword,
        },
      );

      setModals((prev) => ({
        ...prev,
        changePassword: { isOpen: false, userId: null, loading: false },
      }));

      showSuccess("Пароль успешно изменён");
    } catch (error) {
      setError(error.message || "Ошибка при изменении пароля");
    } finally {
      setModals((prev) => ({
        ...prev,
        changePassword: { ...prev.changePassword, loading: false },
      }));
    }
  };

  const handleDeleteUser = async () => {
    setModals((prev) => ({
      ...prev,
      deleteConfirm: { ...prev.deleteConfirm, loading: true },
    }));

    try {
      await api.delete(`/api/v1/admin/users/${modals.deleteConfirm.userId}`);

      setModals((prev) => ({
        ...prev,
        deleteConfirm: {
          isOpen: false,
          userId: null,
          userName: "",
          loading: false,
        },
      }));

      showSuccess("Сотрудник удален");
      await loadUsers();
    } catch (error) {
      setError(error.message || "Ошибка при удалении пользователя");
    } finally {
      setModals((prev) => ({
        ...prev,
        deleteConfirm: { ...prev.deleteConfirm, loading: false },
      }));
    }
  };

  // Управление модальными окнами
  const openEmployeeModal = (user = null) => {
    setModals((prev) => ({
      ...prev,
      employee: { isOpen: true, editingUser: user, loading: false },
    }));
  };

  const openChangePasswordModal = (userId) => {
    setModals((prev) => ({
      ...prev,
      changePassword: { isOpen: true, userId, loading: false },
    }));
  };

  const openDeleteConfirmModal = (userId, userName) => {
    setModals((prev) => ({
      ...prev,
      deleteConfirm: { isOpen: true, userId, userName, loading: false },
    }));
  };

  const closeModals = () => {
    setModals({
      employee: { isOpen: false, editingUser: null, loading: false },
      changePassword: { isOpen: false, userId: null, loading: false },
      deleteConfirm: {
        isOpen: false,
        userId: null,
        userName: "",
        loading: false,
      },
      passwordDisplay: { isOpen: false, username: "", password: "" },
    });
  };

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spinner />
        <span>Загрузка...</span>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <Header />

      {error && (
        <div className={styles.alertError}>
          <Icons.Alert />
          <span>{error}</span>
          <button className={styles.alertClose} onClick={clearError}>
            <Icons.Close />
          </button>
        </div>
      )}

      {success && (
        <div className={styles.alertSuccess}>
          <Icons.Alert />
          <span>{success}</span>
        </div>
      )}

      <div className={styles.usersSection}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Список сотрудников</h2>
          <div className={styles.stats}>{users.length}</div>
          <button
            className={styles.createButton}
            onClick={() => openEmployeeModal()}
          >
            <Icons.Plus />
            <span>Добавить</span>
          </button>
        </div>

        {users.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>👥</div>
            <p>Сотрудники не найдены</p>
            <button
              className={styles.createButton}
              onClick={() => openEmployeeModal()}
            >
              <Icons.Plus />
              <span>Добавить сотрудника</span>
            </button>
          </div>
        ) : (
          <div className={styles.usersList}>
            {users.map((user) => (
              <div key={user.id} className={styles.userCard}>
                <div className={styles.userMain}>
                  <div className={styles.userInfo}>
                    <h3 className={styles.userName}>{user.username}</h3>
                    <div className={styles.userMeta}>
                      <span
                        className={`${styles.roleBadge} ${styles[user.role]}`}
                      >
                        {getRoleDisplayName(user.role)}
                      </span>
                      <span
                        className={`${styles.status} ${
                          user.is_active ? styles.active : styles.inactive
                        }`}
                      >
                        {user.is_active ? "Активен" : "Неактивен"}
                      </span>
                    </div>
                    <p className={styles.restaurants}>
                      {getRestaurantNames(user.restaurants)}
                    </p>
                  </div>

                  <div className={styles.userActions}>
                    <button
                      className={styles.iconButton}
                      onClick={() => openEmployeeModal(user)}
                      title="Изменить"
                    >
                      <Icons.Edit />
                    </button>
                    <button
                      className={styles.iconButton}
                      onClick={() =>
                        handleResetPassword(user.id, user.username)
                      }
                      title="Сбросить пароль"
                    >
                      <Icons.Refresh />
                    </button>
                    <button
                      className={styles.iconButton}
                      onClick={() => openChangePasswordModal(user.id)}
                      title="Сменить пароль"
                    >
                      <Icons.Key />
                    </button>
                    {user.role !== "admin" && (
                      <button
                        className={styles.iconButton}
                        onClick={() =>
                          openDeleteConfirmModal(user.id, user.username)
                        }
                        title="Удалить"
                      >
                        <Icons.Delete />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <EmployeeModal
        isOpen={modals.employee.isOpen}
        onClose={closeModals}
        onSubmit={handleEmployeeSubmit}
        editingUser={modals.employee.editingUser}
        availableRestaurants={availableRestaurants}
        loading={modals.employee.loading}
      />

      <ChangePasswordModal
        isOpen={modals.changePassword.isOpen}
        onClose={closeModals}
        onSubmit={handleChangePassword}
        loading={modals.changePassword.loading}
      />

      <DeleteConfirmModal
        isOpen={modals.deleteConfirm.isOpen}
        onClose={closeModals}
        onConfirm={handleDeleteUser}
        loading={modals.deleteConfirm.loading}
        userName={modals.deleteConfirm.userName}
      />

      <PasswordDisplayModal
        isOpen={modals.passwordDisplay.isOpen}
        onClose={closeModals}
        username={modals.passwordDisplay.username}
        password={modals.passwordDisplay.password}
      />
    </div>
  );
};

// Провайдер для страницы
const EmployeesPage = () => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const router = useRouter();

  const checkAuth = async () => {
    try {
      const userData = await api.get("/api/v1/admin/auth/me");
      setUser(userData);
      setIsAuthenticated(true);
    } catch (error) {
      setIsAuthenticated(false);
      router.push("/login");
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  if (isAuthenticated === null) {
    return (
      <div className={styles.loading}>
        <Spinner />
        <span>Проверка авторизации...</span>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <DashboardProvider user={user}>
      <EmployeesContent />
    </DashboardProvider>
  );
};

export default EmployeesPage;
