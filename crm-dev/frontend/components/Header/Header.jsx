// components/Header/Header.jsx
"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useDashboard } from "@/context/DashboardContext";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import styles from "./Header.module.scss";
import { api } from "@/utils/api";

const BackIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
    <path
      d="M15 18L9 12L15 6"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const UserIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
    <path
      d="M19 21C19 17.134 15.866 14 12 14C8.13401 14 5 17.134 5 21M12 11C9.79086 11 8 9.20914 8 7C8 4.79086 9.79086 3 12 3C14.2091 3 16 4.79086 16 7C16 9.20914 14.2091 11 12 11Z"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <path
      d="M18 6L6 18M6 6l12 12"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const useMenuState = () => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  const toggleMenu = useCallback(() => {
    setMenuOpen((prev) => !prev);
  }, []);

  const closeMenu = useCallback(() => {
    setMenuOpen(false);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        closeMenu();
      }
    };

    if (menuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("touchstart", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
    };
  }, [menuOpen, closeMenu]);

  return { menuOpen, toggleMenu, closeMenu, menuRef };
};

const MenuButton = ({ onClick, isOpen }) => (
  <motion.button
    onClick={onClick}
    className={styles.menuButton}
    whileHover={{ scale: 1.08 }}
    whileTap={{ scale: 0.92 }}
    transition={{ type: "spring", stiffness: 400, damping: 17 }}
    aria-label={isOpen ? "Закрыть меню" : "Открыть меню"}
    aria-expanded={isOpen}
    type="button"
  >
    <UserIcon />
  </motion.button>
);

const RestaurantSelect = ({ options, value, onChange }) => {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef(null);

  const selected = options.find((o) => o.value === value);
  const label = selected?.label || "Выберите ресторан";

  const toggle = () => setIsOpen((v) => !v);
  const close = () => setIsOpen(false);

  useEffect(() => {
    const handler = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        close();
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handler);
      document.addEventListener("touchstart", handler);
    }
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [isOpen]);

  return (
    <div ref={wrapperRef} className={styles.restaurantSelectWrapper}>
      <button
        className={styles.restaurantSelectTrigger}
        onClick={toggle}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        type="button"
      >
        <div className={styles.linkContent}>
          <div className={styles.linkIcon}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path
                d="M3 12L5 10M5 10L12 3L19 10M5 10V20C5 20.5523 5.44772 21 6 21H9M19 10V20C19 20.5523 18.5523 21 18 21H15M9 21C9 19.8954 9.89543 19 11 19H13C14.1046 19 15 19.8954 15 21M9 17V13C9 11.8954 9.89543 11 11 11H13C14.1046 11 15 11.8954 15 13V17"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <span className={styles.linkText}>{label}</span>
        </div>
        <motion.svg
          className={styles.chevron}
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          animate={{ rotate: isOpen ? 90 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <path
            d="M9 6L15 12L9 18"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </motion.svg>
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.ul
            className={styles.restaurantDropdown}
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            role="listbox"
          >
            {options.map((opt) => (
              <li
                key={opt.value}
                className={`${styles.dropdownItem} ${
                  value === opt.value ? styles.selected : ""
                }`}
                onClick={() => {
                  onChange(opt.value);
                  close();
                }}
                role="option"
                aria-selected={value === opt.value}
              >
                {opt.label}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
};

const UserMenu = ({ isOpen, onClose, menuRef }) => {
  const {
    restaurants: userRestaurants,
    selectedRestaurantSlug,
    setRestaurant,
    user,
    isAdmin,
  } = useDashboard();

  const handleRestaurantChange = useCallback(
    (restaurantSlug) => {
      const restaurant = userRestaurants.find((r) => r.slug === restaurantSlug);
      if (restaurant && restaurant.slug !== selectedRestaurantSlug) {
        setRestaurant({ slug: restaurant.slug, id: restaurant.id });
      }
      onClose();
    },
    [userRestaurants, selectedRestaurantSlug, setRestaurant, onClose]
  );

  const handleLogout = useCallback(async () => {
    try {
      await api.post("/api/v1/admin/auth/logout");
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      if (typeof window !== "undefined") {
        localStorage.clear();
        window.location.href = "/login";
      }
    }
  }, []);

  const restaurantOptions = userRestaurants.map((r) => ({
    value: r.slug,
    label: r.name,
  }));

  const getRoleDisplayName = (role) => {
    const roles = {
      admin: "Администратор",
      operator: "Оператор",
      waiter: "Сотрудник зала",
    };
    return roles[role] || role;
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className={styles.contentBlurOverlay}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            className={styles.menuOverlay}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            ref={menuRef}
            className={styles.userMenu}
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.95 }}
            transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
            role="menu"
          >
            <div className={styles.menuHeader}>
              <div className={styles.userContainer}>
                <div className={styles.userAvatar}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <circle
                      cx="12"
                      cy="8"
                      r="3"
                      stroke="currentColor"
                      strokeWidth="1.5"
                    />
                    <path
                      d="M6 20C6 17.7909 7.79086 16 10 16H14C16.2091 16 18 17.7909 18 20"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                    />
                  </svg>
                </div>
                <div className={styles.userInfo}>
                  <div className={styles.userName}>{user?.username}</div>
                  <div className={styles.userRole}>
                    {getRoleDisplayName(user?.role)}
                  </div>
                </div>
              </div>
              <button
                className={styles.closeButton}
                onClick={onClose}
                aria-label="Закрыть меню"
                type="button"
              >
                <CloseIcon />
              </button>
            </div>

            <div className={styles.menuContent}>
              <Link
                href="/"
                className={styles.userMenuLink}
                onClick={onClose}
                role="menuitem"
              >
                <div className={styles.linkContent}>
                  <div className={styles.linkIcon}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                      <path
                        d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                      <path
                        d="M9 22V12h6v10"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                  <span className={styles.linkText}>Главная страница</span>
                </div>
                <motion.svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  className={styles.chevron}
                >
                  <path
                    d="M9 6L15 12L9 18"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </motion.svg>
              </Link>

              {isAdmin && (
                <>
                  <Link
                    href="/employees"
                    className={styles.userMenuLink}
                    onClick={onClose}
                    role="menuitem"
                  >
                    <div className={styles.linkContent}>
                      <div className={styles.linkIcon}>
                        <svg
                          width="20"
                          height="20"
                          viewBox="0 0 24 24"
                          fill="none"
                        >
                          <path
                            d="M12 15C13.6569 15 15 13.6569 15 12C15 10.3431 13.6569 9 12 9C10.3431 9 9 10.3431 9 12C9 13.6569 10.3431 15 12 15Z"
                            stroke="currentColor"
                            strokeWidth="2"
                          />
                          <path
                            d="M19.4 15C19.2669 15.3031 19.1337 15.6062 19.0006 15.9094C18.5298 16.861 18.0589 17.8126 17.5881 18.7641C17.2806 19.3682 16.9731 19.9723 16.6656 20.5764C16.255 21.382 15.4388 22 14.5 22H9.5C8.56122 22 7.745 21.382 7.33437 20.5764C7.02687 19.9723 6.71937 19.3682 6.41187 18.7641C5.94106 17.8126 5.47025 16.861 4.99944 15.9094C4.86625 15.6062 4.73312 15.3031 4.6 15"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                          />
                          <path
                            d="M19.4 9C19.2669 8.69687 19.1337 8.39375 19.0006 8.09063C18.5298 7.13897 18.0589 6.18741 17.5881 5.23584C17.2806 4.63172 16.9731 4.02766 16.6656 3.42359C16.255 2.61803 15.4388 2 14.5 2H9.5C8.56122 2 7.745 2.61803 7.33437 3.42359C7.02687 4.02766 6.71937 4.63172 6.41187 5.23584C5.94106 6.18741 5.47025 7.13897 4.99944 8.09063C4.86625 8.39375 4.73312 8.69687 4.6 9"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                          />
                        </svg>
                      </div>
                      <span className={styles.linkText}>
                        Управление сотрудниками
                      </span>
                    </div>
                    <motion.svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      className={styles.chevron}
                    >
                      <path
                        d="M9 6L15 12L9 18"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </motion.svg>
                  </Link>
                  <Link
                    href="/admin"
                    className={styles.userMenuLink}
                    onClick={onClose}
                    role="menuitem"
                  >
                    <div className={styles.linkContent}>
                      <div className={styles.linkIcon}>
                        <svg
                          width="20"
                          height="20"
                          viewBox="0 0 24 24"
                          fill="none"
                        >
                          <path
                            d="M3 3h18v4H3V3zm0 7h18v4H3v-4zm0 7h18v4H3v-4z"
                            stroke="currentColor"
                            strokeWidth="2"
                          />
                        </svg>
                      </div>
                      <span className={styles.linkText}>Админка</span>
                    </div>
                    <motion.svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      className={styles.chevron}
                    >
                      <path
                        d="M9 6L15 12L9 18"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </motion.svg>
                  </Link>
                </>
              )}

              <div className={styles.sidebarContent}>
                <div className={styles.section}>
                  <RestaurantSelect
                    options={restaurantOptions}
                    value={selectedRestaurantSlug || ""}
                    onChange={handleRestaurantChange}
                  />
                </div>

                <div className={styles.section}>
                  <button
                    onClick={handleLogout}
                    className={styles.logoutButton}
                    type="button"
                  >
                    <svg
                      className={styles.logoutIcon}
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                      />
                    </svg>
                    Выйти из системы
                  </button>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

export default function Header() {
  const { menuOpen, toggleMenu, closeMenu, menuRef } = useMenuState();
  const { restaurants, selectedRestaurantSlug } = useDashboard();

  const currentRestaurant = restaurants.find(
    (r) => r.slug === selectedRestaurantSlug
  );

  return (
    <>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.leftSection}>
            {currentRestaurant ? (
              <div className={styles.restaurantCurrent}>
                <span className={styles.restaurantName}>
                  {currentRestaurant.name}
                </span>
              </div>
            ) : (
              <span className={styles.placeholder}>Выберите ресторан</span>
            )}
          </div>

          <div className={styles.rightSection}>
            <MenuButton onClick={toggleMenu} isOpen={menuOpen} />
          </div>
        </div>
      </header>
      <UserMenu isOpen={menuOpen} onClose={closeMenu} menuRef={menuRef} />
    </>
  );
}
