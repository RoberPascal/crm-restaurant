// utils/phoneFormatter.js

/**
 * Форматирует номер телефона в красивый российский формат
 * @param {string} phone - Сырой номер телефона (любого формата)
 * @returns {string} - Отформатированный номер
 */
export function formatPhoneDisplay(phone) {
  if (!phone) return "";

  // Оставляем только цифры
  const cleaned = phone.replace(/\D/g, "");

  // Если номер слишком короткий, возвращаем как есть
  if (cleaned.length < 10) return phone;

  // Российские номера
  if (
    cleaned.length === 11 &&
    (cleaned.startsWith("7") || cleaned.startsWith("8"))
  ) {
    // Формат: +7 (XXX) XXX-XX-XX
    const match = cleaned.match(/^[78]?(\d{3})(\d{3})(\d{2})(\d{2})$/);
    if (match) {
      return `+7 (${match[1]}) ${match[2]}-${match[3]}-${match[4]}`;
    }
  }

  // Международные номера или другие форматы
  if (cleaned.length === 12 && cleaned.startsWith("7")) {
    const match = cleaned.match(/^7(\d{3})(\d{3})(\d{2})(\d{2})$/);
    if (match) {
      return `+7 (${match[1]}) ${match[2]}-${match[3]}-${match[4]}`;
    }
  }

  // Для других случаев возвращаем очищенный номер
  return `+${cleaned}`;
}

/**
 * Нормализует номер телефона для API (только цифры с кодом страны)
 * @param {string} phone - Любой формат номера
 * @returns {string} - Нормализованный номер (79991234567)
 */
export function normalizePhone(phone) {
  if (!phone) return "";

  const cleaned = phone.replace(/\D/g, "");

  // Если номер начинается с 8, заменяем на 7
  if (cleaned.length === 11 && cleaned.startsWith("8")) {
    return "7" + cleaned.slice(1);
  }

  // Если номер без кода страны, добавляем 7
  if (cleaned.length === 10) {
    return "7" + cleaned;
  }

  return cleaned;
}

/**
 * Проверяет валидность номера телефона
 * @param {string} phone - Номер телефона
 * @returns {boolean} - Валиден ли номер
 */
export function isValidPhone(phone) {
  if (!phone) return false;

  const cleaned = phone.replace(/\D/g, "");

  // Российские номера: 11 цифр (7XXXXXXXXXX) или 10 цифр (XXXXXXXXXX)
  return (
    (cleaned.length === 11 && cleaned.startsWith("7")) ||
    cleaned.length === 10 ||
    (cleaned.length === 12 && cleaned.startsWith("77"))
  ); // Казахстан и др.
}
