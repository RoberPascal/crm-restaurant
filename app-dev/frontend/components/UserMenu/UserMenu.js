// components/Header/Header.js (только UserMenu компонент)
const UserMenu = ({ isOpen, onClose, menuRef }) => {
  const user = useTelegramUser();

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
            rx="2"
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
            r="4"
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
    ...(user
      ? [
          {
            href: "/logout",
            label: "Выйти",
            icon: (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M9 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H9"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
                <path
                  d="M16 17L21 12L16 7"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
                <path
                  d="M21 12H9"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            ),
          },
        ]
      : [
          {
            href: "/login",
            label: "Войти",
            icon: (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M9 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H9"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
                <path
                  d="M16 17L21 12L16 7"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
                <path
                  d="M21 12H9"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            ),
          },
        ]),
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
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
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
                </div>
                <div className={styles.userText}>
                  <span className={styles.menuTitle}>Аккаунт</span>
                  <span className={styles.userStatus}>
                    {user ? "Авторизован" : "Гость"}
                  </span>
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

            <div className={styles.menuFooter}>
              <span className={styles.footerText}>
                {user ? `ID: ${user.id}` : "Войдите для бронирований"}
              </span>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
