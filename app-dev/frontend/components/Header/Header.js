"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import styles from "./Header.module.scss";

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

const ShareIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
    <path
      d="M18 8C19.6569 8 21 6.65685 21 5C21 3.34315 19.6569 2 18 2C16.3431 2 15 3.34315 15 5C15 6.65685 16.3431 8 18 8Z"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M6 15C7.65685 15 9 13.6569 9 12C9 10.3431 7.65685 9 6 9C4.34315 9 3 10.3431 3 12C3 13.6569 4.34315 15 6 15Z"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M18 22C19.6569 22 21 20.6569 21 19C21 17.3431 19.6569 16 18 16C16.3431 16 15 17.3431 15 19C15 20.6569 16.3431 22 18 22Z"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M8.59 13.51L15.42 17.49"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <path
      d="M15.41 6.51L8.59 10.49"
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

const CopyIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <rect
      x="9"
      y="9"
      width="13"
      height="13"
      rx="2"
      stroke="currentColor"
      strokeWidth="1.8"
    />
    <path
      d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
    />
  </svg>
);

const CheckIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
    <path
      d="M20 6L9 17L4 12"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

// Хук для управления состоянием меню
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

  return {
    menuOpen,
    toggleMenu,
    closeMenu,
    menuRef,
  };
};

// Хук для шеринга
// Хук для шеринга
const useShare = () => {
  const [showShareModal, setShowShareModal] = useState(false);
  const [copied, setCopied] = useState(false);

  const shareUrl = typeof window !== "undefined" ? window.location.href : "";

  // Создаем ссылку на бота с закодированным URL ресторана
  const botShareUrl = `https://t.me/PticaTest_Bot?start=${encodeURIComponent(
    btoa(shareUrl), // Кодируем URL ресторана в base64
  )}`;

  const openShareModal = useCallback(() => {
    setShowShareModal(true);
  }, []);

  const closeShareModal = useCallback(() => {
    setShowShareModal(false);
    setCopied(false);
  }, []);

  // Функция для копирования ссылки на бота
  const copyBotLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(botShareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      // Fallback для старых браузеров
      const textArea = document.createElement("textarea");
      textArea.value = botShareUrl;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [botShareUrl]);

  const shareNative = useCallback(async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: document.title,
          url: botShareUrl, // Используем ссылку на бота для нативного шеринга
        });
      } catch (err) {
        // Пользователь отменил шеринг
      }
    } else {
      openShareModal();
    }
  }, [botShareUrl, openShareModal]);

  return {
    showShareModal,
    openShareModal: shareNative,
    closeShareModal,
    copyToClipboard: copyBotLink, // Передаем функцию копирования ссылки на бота
    copied,
    shareUrl: botShareUrl, // Теперь shareUrl это ссылка на бота
  };
};

// Кнопка меню
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

// Кнопка поделиться
const ShareButton = ({ onClick }) => (
  <motion.button
    onClick={onClick}
    className={styles.shareButton}
    whileHover={{ scale: 1.08 }}
    whileTap={{ scale: 0.92 }}
    transition={{ type: "spring", stiffness: 400, damping: 17 }}
    aria-label="Поделиться рестораном"
    type="button"
  >
    <ShareIcon />
  </motion.button>
);

// Модалка шеринга
const ShareModal = ({ isOpen, onClose, onCopy, copied, shareUrl }) => {
  // Создаем ссылку на бота с закодированным URL ресторана
  const botShareUrl = `https://t.me/PticaTest_Bot?start=${encodeURIComponent(
    btoa(shareUrl), // Кодируем URL ресторана в base64
  )}`;

  const shareOptions = [
    {
      name: "Telegram",
      icon: "Tg",
      color: "#0088cc",
      url: botShareUrl, // Используем ту же ссылку на бота
    },
    {
      name: "WhatsApp",
      icon: "Wa",
      color: "#25D366",
      url: `https://wa.me/?text=${encodeURIComponent(
        `Посмотри этот бар! ${botShareUrl}`, // Тоже используем ссылку на бота
      )}`,
    },
    {
      name: "VK",
      icon: "Vk",
      color: "#4C75A3",
      url: `https://vk.com/share.php?url=${encodeURIComponent(botShareUrl)}`, // И здесь ссылку на бота
    },
  ];

  // Функция для копирования ссылки на бота
  const copyBotLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(botShareUrl);
      if (onCopy) onCopy();
    } catch (err) {
      // Fallback для старых браузеров
      const textArea = document.createElement("textarea");
      textArea.value = botShareUrl;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      if (onCopy) onCopy();
    }
  }, [botShareUrl, onCopy]);

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
            className={styles.shareModal}
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.95 }}
            transition={{
              duration: 0.25,
              ease: [0.4, 0, 0.2, 1],
            }}
            role="dialog"
            aria-label="Поделиться баром"
          >
            <div className={styles.modalHeader}>
              <h3 className={styles.modalTitle}>Поделиться баром</h3>
              <button
                className={styles.closeButton}
                onClick={onClose}
                aria-label="Закрыть"
              >
                <CloseIcon />
              </button>
            </div>

            <div className={styles.shareContent}>
              <div className={styles.shareOptions}>
                {shareOptions.map((option) => (
                  <a
                    key={option.name}
                    href={option.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.shareOption}
                    style={{ "--accent-color": option.color }}
                    aria-label={`Поделиться в ${option.name}`}
                  >
                    <span className={styles.shareIcon}>{option.icon}</span>
                    <span className={styles.shareName}>{option.name}</span>
                  </a>
                ))}
              </div>

              <div className={styles.copySection}>
                <div className={styles.urlDisplay}>
                  <span className={styles.urlText}>
                    {botShareUrl.length > 40
                      ? `${botShareUrl.slice(0, 40)}...`
                      : botShareUrl}
                  </span>
                </div>
                <button
                  onClick={copyBotLink} // Используем функцию копирования ссылки на бота
                  className={`${styles.copyButton} ${
                    copied ? styles.copied : ""
                  }`}
                  aria-label={
                    copied ? "Скопировано" : "Скопировать ссылку на бота"
                  }
                >
                  {copied ? <CheckIcon /> : <CopyIcon />}
                  {copied ? "Скопировано" : "Копировать"}
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

// Меню пользователя (остается без изменений)
const UserMenu = ({ isOpen, onClose, menuRef }) => {
  const menuLinks = [
    {
      href: "/bookings",
      label: "Мои бронирования",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <rect
            x="3"
            y="4"
            width="18"
            height="17"
            rx="1.5"
            stroke="currentColor"
            strokeWidth="1.5"
          />
          <path
            d="M8 2V6M16 2V6"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <path
            d="M3 10H21"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <path
            d="M8 14H8.01M12 14H12.01M16 14H16.01M8 17H8.01M12 17H12.01M16 17H16.01"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      ),
    },
    {
      href: "/profile",
      label: "Личные данные",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <circle
            cx="12"
            cy="8"
            r="3.5"
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
      ),
    },
  ];

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
            transition={{
              duration: 0.25,
              ease: [0.4, 0, 0.2, 1],
            }}
            role="menu"
          >
            <div className={styles.menuHeader}>
              <div className={styles.userInfo}>
                <div className={styles.userAvatar}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
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
              </div>
              <button
                className={styles.closeButton}
                onClick={onClose}
                aria-label="Закрыть меню"
              >
                <CloseIcon />
              </button>
            </div>

            <div className={styles.menuContent}>
              {menuLinks.map((link, index) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className={styles.userMenuLink}
                  onClick={onClose}
                  role="menuitem"
                >
                  <div className={styles.linkContent}>
                    <div className={styles.linkIcon}>{link.icon}</div>
                    <span className={styles.linkText}>{link.label}</span>
                  </div>
                  <motion.svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    className={styles.chevron}
                    initial={{ x: -4, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    transition={{ delay: index * 0.05 + 0.1 }}
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
              ))}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

export const Header = ({ showBackButton = true }) => {
  const { menuOpen, toggleMenu, closeMenu, menuRef } = useMenuState();
  const {
    showShareModal,
    openShareModal,
    closeShareModal,
    copyToClipboard,
    copied,
  } = useShare();

  return (
    <>
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <div className={styles.leftSection}>
            {showBackButton && (
              <motion.div
                whileHover={{ scale: 1.08 }}
                whileTap={{ scale: 0.92 }}
                transition={{ type: "spring", stiffness: 400, damping: 17 }}
              >
                <Link
                  href="/"
                  className={styles.backButton}
                  aria-label="Назад к списку баров"
                >
                  <BackIcon />
                </Link>
              </motion.div>
            )}
          </div>

          <div className={styles.rightSection}>
            <ShareButton onClick={openShareModal} />
            <MenuButton onClick={toggleMenu} isOpen={menuOpen} />
          </div>
        </div>

        <UserMenu isOpen={menuOpen} onClose={closeMenu} menuRef={menuRef} />
        <ShareModal
          isOpen={showShareModal}
          onClose={closeShareModal}
          onCopy={copyToClipboard}
          copied={copied}
          shareUrl={typeof window !== "undefined" ? window.location.href : ""}
        />
      </header>
    </>
  );
};
