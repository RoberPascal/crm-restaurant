# app/core/valodation_utils.py
import re
import phonenumbers
from typing import Optional, Tuple, Dict, Any, List
from datetime import date, datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

# Импортируем после определения logger
from .time_utils import strict_parse_date, parse_time_strict, get_moscow_today
from .config import settings

# Регулярные выражения для валидации
NAME_PATTERN = re.compile(r'^[a-zA-Zа-яА-ЯёЁ\s\-\.\']{2,50}$')
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
PHONE_PATTERN = re.compile(r'^[\+]?[0-9\s\-\(\)]{10,20}$')
RESTAURANT_SLUG_PATTERN = re.compile(r'^[a-z0-9\-]{1,50}$')
TABLE_NUMBER_PATTERN = re.compile(r'^[A-Za-z0-9\-_ ]{1,20}$')
LOCATION_MARK_PATTERN = re.compile(r'^[A-Za-z0-9\-_ ]{0,50}$')

# Зарезервированные имена и slug'ы
RESERVED_SLUGS = {
    'admin', 'api', 'static', 'media', 'cdn', 'blog', 'support', 
    'help', 'contact', 'about', 'terms', 'privacy', 'login', 
    'logout', 'register', 'dashboard', 'profile'
}

DISPOSABLE_EMAIL_DOMAINS = {
    'tempmail.com', 'throwaway.com', 'guerrillamail.com',
    'mailinator.com', '10minutemail.com', 'fakeinbox.com',
    'yopmail.com', 'trashmail.com', 'disposablemail.com'
}

# Опасные паттерны для защиты от инъекций
DANGEROUS_PATTERNS = [
    r'<script', r'javascript:', r'onload=', r'onerror=', r'onclick=',
    r'vbscript:', r'expression\(', r'alert\(', r'confirm\(', r'prompt\(',
    r'SELECT.*FROM', r'INSERT.*INTO', r'DROP.*TABLE', r'DELETE.*FROM',
    r'UPDATE.*SET', r'UNION.*SELECT', r'OR.*1=1', r'AND.*1=1'
]


class ValidationError(Exception):
    """Базовое исключение для ошибок валидации"""
    def __init__(self, message: str, field: str = None):
        self.message = message
        self.field = field
        super().__init__(self.message)


def validate_person_name(name: str) -> Tuple[bool, str]:
    """
    Валидация имени человека с защитой от инъекций и XSS.
    """
    if not name or not isinstance(name, str):
        return False, "Name is required"
    
    name = name.strip()
    
    if len(name) < 2:
        return False, "Name must be at least 2 characters long"
    
    if len(name) > 50:
        return False, "Name cannot exceed 50 characters"
    
    if not NAME_PATTERN.match(name):
        return False, "Name can only contain letters, spaces, hyphens, dots and apostrophes"
    
    # Проверка на потенциально опасные последовательности
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            logger.warning("Potential injection attempt detected in name", name=name[:50])
            return False, "Invalid name format"
    
    # Проверка на повторяющиеся пробелы
    if '  ' in name:
        return False, "Name contains multiple consecutive spaces"
    
    return True, ""


def validate_phone_number(phone: str, country: str = "RU") -> Tuple[bool, str]:
    """
    Валидация номера телефона с использованием phonenumbers library.
    Возвращает нормализованный номер в формате E164.
    """
    if not phone or not isinstance(phone, str):
        return False, "Phone number is required"
    
    phone = phone.strip()
    
    # Базовая проверка формата
    if not PHONE_PATTERN.match(phone):
        return False, "Invalid phone number format"
    
    try:
        # Парсинг номера
        parsed = phonenumbers.parse(phone, country)
        
        if not phonenumbers.is_valid_number(parsed):
            return False, "Invalid phone number"
        
        # Проверка что номер не из диапазона тестовых номеров
        if phonenumbers.is_possible_number(parsed) and not phonenumbers.is_valid_number(parsed):
            return False, "Phone number appears to be invalid"
        
        # Нормализация номера
        normalized = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        
        # Дополнительная проверка для российских номеров
        if country == "RU" and not normalized.startswith('+7'):
            return False, "Russian phone numbers must start with +7"
        
        return True, normalized
        
    except phonenumbers.NumberParseException as e:
        logger.debug("Phone number parsing failed", phone=phone, error=str(e))
        return False, "Invalid phone number format"


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Валидация email адреса с проверкой disposable доменов.
    """
    if not email or not isinstance(email, str):
        return False, "Email is required"
    
    email = email.strip().lower()
    
    if len(email) > 100:
        return False, "Email cannot exceed 100 characters"
    
    if not EMAIL_PATTERN.match(email):
        return False, "Invalid email format"
    
    # Проверка disposable email domains
    domain = email.split('@')[-1].lower()
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return False, "Disposable email addresses are not allowed"
    
    # Проверка на опасные символы
    if any(char in email for char in ['<', '>', '"', "'", '(', ')', ';', ':', '\\', '/', '[', ']']):
        return False, "Email contains invalid characters"
    
    return True, email


def validate_restaurant_slug(slug: str) -> Tuple[bool, str]:
    """
    Валидация slug ресторана с проверкой зарезервированных имен.
    """
    if not slug or not isinstance(slug, str):
        return False, "Restaurant slug is required"
    
    slug = slug.strip().lower()
    
    if len(slug) < 1:
        return False, "Slug cannot be empty"
    
    if len(slug) > 50:
        return False, "Slug cannot exceed 50 characters"
    
    if not RESTAURANT_SLUG_PATTERN.match(slug):
        return False, "Slug can only contain lowercase letters, numbers and hyphens"
    
    # Зарезервированные slug'ы
    if slug in RESERVED_SLUGS:
        return False, "This restaurant slug is reserved"
    
    # Проверка на последовательные дефисы
    if '--' in slug:
        return False, "Slug cannot contain consecutive hyphens"
    
    # Проверка на начало/конец с дефиса
    if slug.startswith('-') or slug.endswith('-'):
        return False, "Slug cannot start or end with a hyphen"
    
    return True, slug


def validate_table_number(table_number: str) -> Tuple[bool, str]:
    """
    Валидация номера стола.
    """
    if not table_number or not isinstance(table_number, str):
        return False, "Table number is required"
    
    table_number = table_number.strip()
    
    if len(table_number) < 1:
        return False, "Table number cannot be empty"
    
    if len(table_number) > 20:
        return False, "Table number cannot exceed 20 characters"
    
    if not TABLE_NUMBER_PATTERN.match(table_number):
        return False, "Table number can only contain letters, numbers, spaces, hyphens and underscores"
    
    return True, table_number


def validate_location_mark(location_mark: str) -> Tuple[bool, str]:
    """
    Валидация метки расположения стола.
    """
    if not location_mark:
        return True, ""  # Необязательное поле
    
    if not isinstance(location_mark, str):
        return False, "Location mark must be a string"
    
    location_mark = location_mark.strip()
    
    if len(location_mark) > 50:
        return False, "Location mark cannot exceed 50 characters"
    
    if not LOCATION_MARK_PATTERN.match(location_mark):
        return False, "Location mark can only contain letters, numbers, spaces, hyphens and underscores"
    
    return True, location_mark


def validate_seats_configuration(seats_min: int, seats_max: int) -> Tuple[bool, str]:
    """
    Валидация конфигурации мест за столом.
    """
    if not isinstance(seats_min, int) or not isinstance(seats_max, int):
        return False, "Seats configuration must be integers"
    
    if seats_min < 1:
        return False, "Minimum seats must be at least 1"
    
    if seats_max < 1:
        return False, "Maximum seats must be at least 1"
    
    if seats_min > seats_max:
        return False, "Minimum seats cannot exceed maximum seats"
    
    if seats_max > 50:  # Разумный лимит
        return False, "Maximum seats cannot exceed 50"
    
    return True, ""


def validate_booking_parameters(restaurant_slug: str, 
                              booking_date: str, 
                              booking_time: str,
                              client_name: str,
                              client_phone: str,
                              guests_count: int = 1) -> Tuple[bool, str, dict]:
    """
    Комплексная валидация параметров бронирования.
    Возвращает нормализованные данные для использования.
    """
    normalized_data = {}
    
    try:
        # Валидация slug ресторана
        is_valid_slug, slug_error = validate_restaurant_slug(restaurant_slug)
        if not is_valid_slug:
            return False, slug_error, {}
        normalized_data['restaurant_slug'] = restaurant_slug.lower()
        
        # Валидация даты
        parsed_date = strict_parse_date(booking_date)
        if not parsed_date:
            return False, "Invalid date format", {}
        
        # Проверка что дата не в прошлом
        today = get_moscow_today()
        if parsed_date < today:
            return False, "Cannot book past dates", {}
        normalized_data['booking_date'] = parsed_date
        
        # Валидация времени
        parsed_time = parse_time_strict(booking_time)
        if not parsed_time:
            return False, "Invalid time format", {}
        normalized_data['booking_time'] = parsed_time
        
        # Валидация имени
        is_valid_name, name_error = validate_person_name(client_name)
        if not is_valid_name:
            return False, name_error, {}
        normalized_data['client_name'] = client_name.strip()
        
        # Валидация телефона
        is_valid_phone, phone_normalized = validate_phone_number(client_phone)
        if not is_valid_phone:
            return False, phone_normalized, {}
        normalized_data['client_phone'] = phone_normalized
        
        # Валидация количества гостей
        if not isinstance(guests_count, int) or guests_count < 1:
            return False, "Guests count must be a positive integer", {}
        
        if guests_count > 50:  # Разумный лимит
            return False, "Too many guests", {}
        normalized_data['guests_count'] = guests_count
        
        # Проверка что время бронирования не слишком далеко в будущем
        max_booking_days = getattr(settings, 'MAX_BOOKING_DAYS', 90)
        max_future_date = today + timedelta(days=max_booking_days)
        if parsed_date > max_future_date:
            return False, f"Booking too far in future. Maximum is {max_booking_days} days", {}
        
        return True, "", normalized_data
        
    except Exception as e:
        logger.error("Unexpected error during booking validation", error=str(e))
        return False, "Validation error occurred", {}


def validate_restaurant_schedule(schedule: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Валидация расписания ресторана.
    """
    if not isinstance(schedule, list):
        return False, "Schedule must be a list"
    
    if len(schedule) == 0:
        return True, ""  # Пустое расписание допустимо
    
    seen_days = set()
    
    for day_schedule in schedule:
        if not isinstance(day_schedule, dict):
            return False, "Each schedule item must be a dictionary"
        
        day = day_schedule.get('day')
        open_time = day_schedule.get('open')
        close_time = day_schedule.get('close')
        
        # Проверка дня недели
        if not isinstance(day, int) or day < 0 or day > 6:
            return False, f"Invalid day value: {day}. Must be between 0 and 6"
        
        if day in seen_days:
            return False, f"Duplicate day found: {day}"
        seen_days.add(day)
        
        # Проверка времени открытия
        open_time_valid = parse_time_strict(open_time) if open_time else False
        if not open_time_valid:
            return False, f"Invalid open time: {open_time}"
        
        # Проверка времени закрытия
        close_time_valid = parse_time_strict(close_time) if close_time else False
        if not close_time_valid:
            return False, f"Invalid close time: {close_time}"
        
        # Проверка что время открытия раньше времени закрытия
        if open_time >= close_time:
            return False, f"Open time {open_time} must be before close time {close_time}"
    
    return True, ""


def sanitize_user_input(input_str: str, field_type: str = "text", max_length: int = 255) -> str:
    """
    Безопасная санитизация пользовательского ввода.
    """
    if not input_str or not isinstance(input_str, str):
        return ""
    
    # Обрезка по максимальной длине
    sanitized = input_str.strip()[:max_length]
    
    # Удаление потенциально опасных символов в зависимости от типа поля
    if field_type == "text":
        sanitized = re.sub(r'[<>"\'&]', '', sanitized)
    elif field_type == "name":
        sanitized = re.sub(r'[<>"\'&;]', '', sanitized)
    elif field_type == "email":
        sanitized = re.sub(r'[<>"\'&;]', '', sanitized)
    elif field_type == "phone":
        sanitized = re.sub(r'[^0-9+\-\s\(\)]', '', sanitized)
    
    return sanitized


def validate_and_sanitize_booking_data(data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Комплексная валидация и санитизация данных бронирования.
    """
    try:
        sanitized_data = {}
        
        # Обязательные поля
        required_fields = ['restaurant_slug', 'booking_date', 'booking_time', 'client_name', 'client_phone']
        for field in required_fields:
            if field not in data or not data[field]:
                return False, f"Missing required field: {field}", {}
        
        # Санитизация и валидация
        restaurant_slug = sanitize_user_input(data['restaurant_slug'], 'text', 50)
        booking_date = sanitize_user_input(data['booking_date'], 'text', 10)
        booking_time = sanitize_user_input(data['booking_time'], 'text', 5)
        client_name = sanitize_user_input(data['client_name'], 'name', 50)
        client_phone = sanitize_user_input(data['client_phone'], 'phone', 20)
        guests_count = data.get('guests_count', 1)
        
        # Комплексная валидация
        return validate_booking_parameters(
            restaurant_slug=restaurant_slug,
            booking_date=booking_date,
            booking_time=booking_time,
            client_name=client_name,
            client_phone=client_phone,
            guests_count=guests_count
        )
        
    except Exception as e:
        logger.error("Booking data validation error", error=str(e))
        return False, "Data validation failed", {}


# Декоратор для валидации входящих данных
def validate_input(validation_func):
    """
    Декоратор для автоматической валидации входных данных функций.
    """
    def wrapper(*args, **kwargs):
        # Здесь можно добавить логику валидации
        # Например, проверку типов, обязательных полей и т.д.
        return validation_func(*args, **kwargs)
    return wrapper