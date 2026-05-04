"use client";

import { motion, AnimatePresence } from "framer-motion";
import styles from "./DeleteAccountModal.module.scss";

export const DeleteAccountModal = ({ isOpen, onClose, onConfirm }) => {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className={styles.overlay}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            className={styles.modal}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
          >
            <h2 className={styles.title}>
              Подтвердите удаление учетной записи
            </h2>
            <p className={styles.description}>
              Все данные, связанные с ней, также будут удалены. Удалить учетную
              запись?
            </p>
            <div className={styles.buttons}>
              <button
                className={`${styles.button} ${styles.cancelButton}`}
                onClick={onClose}
              >
                Отмена
              </button>
              <button
                className={`${styles.button} ${styles.confirmButton}`}
                onClick={onConfirm}
              >
                Подтверждаю
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
