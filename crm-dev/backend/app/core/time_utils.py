# app/core/time_utils.py
from datetime import datetime, date, time, timedelta
from typing import Union, Optional, Tuple
from zoneinfo import ZoneInfo
import re
import structlog

logger = structlog.get_logger(__name__)

# Импортируем settings
from app.core.config import settings

# Константы для безопасности и производительности
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
MAX_BOOKING_DAYS = 365  # Максимальный период бронирования
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TIME_PATTERN = re.compile(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$')

# Кэш для часто используемых datetime объектов (dict для атомарного обновления)
_moscow_cache = {"value": None, "updated_at": 0}
_CACHE_TIMEOUT = 1.0  # секунды

# Кэш для локального времени
_local_cache = {"value": None, "updated_at": 0}


def get_local_timezone():
    """Получение локального часового пояса из настроек"""
    timezone_str = getattr(settings, 'TIMEZONE', 'Europe/Moscow')
    try:
        return ZoneInfo(timezone_str)
    except Exception:
        # Fallback to Moscow timezone
        return MOSCOW_TZ


def get_current_time() -> datetime:
    """
    Return current time in local timezone (aware datetime) with performance optimization.
    Uses caching to avoid frequent system calls.
    """
    import time as time_module
    current_time = time_module.time()
    
    cached = _local_cache
    if (cached["value"] is None or 
        current_time - cached["updated_at"] > _CACHE_TIMEOUT):
        local_tz = get_local_timezone()
        now = datetime.now(tz=local_tz)
        _local_cache.update({"value": now, "updated_at": current_time})
        return now
    
    return cached["value"]


def get_moscow_now() -> datetime:
    """
    Return current time in Moscow tz (aware datetime) with performance optimization.
    Uses caching to avoid frequent system calls.
    """
    import time as time_module
    current_time = time_module.time()
    
    cached = _moscow_cache
    if (cached["value"] is None or 
        current_time - cached["updated_at"] > _CACHE_TIMEOUT):
        now = datetime.now(tz=MOSCOW_TZ)
        _moscow_cache.update({"value": now, "updated_at": current_time})
        return now
    
    return cached["value"]


def get_moscow_today() -> date:
    """Get current date in Moscow timezone with caching."""
    return get_moscow_now().date()


def get_local_today() -> date:
    """Get current date in local timezone with caching."""
    return get_current_time().date()


def to_moscow_time(dt: Union[datetime, date]) -> datetime:
    """
    Convert naive or aware datetime/date to Moscow-aware datetime.
    Enhanced with input validation.
    
    ВАЖНО: Naive datetime из БД уже в московском времени!
    Мы храним start_datetime/end_datetime как naive в московском времени.
    """
    if not isinstance(dt, (datetime, date)):
        raise ValueError("Input must be datetime or date")
    
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time.min)
    
    if dt.tzinfo is None:
        # БД хранит naive datetime УЖЕ в московском времени
        # Просто добавляем timezone info без конвертации
        return dt.replace(tzinfo=MOSCOW_TZ)
    
    return dt.astimezone(MOSCOW_TZ)


def to_local_time(dt: Union[datetime, date]) -> datetime:
    """
    Convert naive or aware datetime/date to local-aware datetime.
    Enhanced with input validation.
    """
    if not isinstance(dt, (datetime, date)):
        raise ValueError("Input must be datetime or date")
    
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time.min)
    
    local_tz = get_local_timezone()
    
    if dt.tzinfo is None:
        # Assume naive datetime is in UTC for consistency
        return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(local_tz)
    
    return dt.astimezone(local_tz)


def utc_to_local(utc_dt: datetime) -> datetime:
    """Конвертация UTC времени в локальный пояс"""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=ZoneInfo("UTC"))
    return utc_dt.astimezone(get_local_timezone())


def local_to_utc(local_dt: datetime) -> datetime:
    """Конвертация локального времени в UTC"""
    local_tz = get_local_timezone()
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=local_tz)
    return local_dt.astimezone(ZoneInfo("UTC"))


def strict_parse_date(date_str: str) -> Optional[date]:
    """
    Strictly parse date string in YYYY-MM-DD format.
    Returns None on any error or invalid date.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    # Validate format with regex first
    if not DATE_PATTERN.match(date_str.strip()):
        return None
    
    try:
        # Use fromisoformat for strict parsing
        parsed_date = date.fromisoformat(date_str)
        
        # Additional validation for realistic dates
        if parsed_date.year < 2020 or parsed_date.year > 2030:
            return None
            
        return parsed_date
    except (ValueError, TypeError):
        return None


def parse_time_strict(time_str: str) -> Optional[time]:
    """
    Strictly parse time string in HH:MM format.
    Returns None on any error.
    """
    if not time_str or not isinstance(time_str, str):
        return None
    
    # Validate format with regex
    if not TIME_PATTERN.match(time_str.strip()):
        return None
    
    try:
        hours, minutes = map(int, time_str.split(':'))
        return time(hour=hours, minute=minutes)
    except (ValueError, TypeError):
        return None


def parse_date_to_moscow(date_str: str) -> Optional[date]:
    """
    Parse ISO-8601-ish strings to Moscow date with enhanced security.
    Only accepts well-formed dates.
    """
    if not date_str:
        return None
        
    s = date_str.strip()
    
    # First try strict date-only parsing
    strict_date = strict_parse_date(s)
    if strict_date:
        return strict_date
    
    # Fallback to datetime parsing with security limits
    try:
        # Security: Limit input length
        if len(s) > 30:
            return None
            
        # Handle Zulu time
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        
        # Parse with timezone awareness
        dt = datetime.fromisoformat(s)
        moscow_dt = to_moscow_time(dt)
        return moscow_dt.date()
        
    except (ValueError, TypeError):
        logger.warning("Failed to parse date string", date_str=date_str)
        return None


def is_past_date(check_date: Union[date, str]) -> bool:
    """
    Check if date is in the past (before today).
    Returns False for invalid dates.
    """
    if isinstance(check_date, str):
        parsed = strict_parse_date(check_date)
        if parsed is None:
            return False  # Invalid dates are not considered past
        check_date = parsed
    
    return check_date < get_moscow_today()


def is_future_date(check_date: Union[date, str], max_days: int = MAX_BOOKING_DAYS) -> bool:
    """
    Check if date is too far in the future.
    Returns False for invalid dates.
    """
    if max_days > MAX_BOOKING_DAYS:
        max_days = MAX_BOOKING_DAYS  # Security limit
    
    if isinstance(check_date, str):
        parsed = strict_parse_date(check_date)
        if parsed is None:
            return False
        check_date = parsed
    
    max_future_date = get_moscow_today() + timedelta(days=max_days)
    return check_date > max_future_date


def validate_booking_datetime(booking_date: Union[date, str], 
                            booking_time: Union[time, str],
                            restaurant_cutoff: str = "18:00",
                            max_booking_days: int = 30) -> Tuple[bool, Optional[str]]:
    """
    Comprehensive validation for booking date and time.
    Returns (is_valid, error_message)
    """
    # Parse and validate date
    if isinstance(booking_date, str):
        parsed_date = strict_parse_date(booking_date)
        if not parsed_date:
            return False, "Invalid date format"
        booking_date = parsed_date
    
    # Parse and validate time
    if isinstance(booking_time, str):
        parsed_time = parse_time_strict(booking_time)
        if not parsed_time:
            return False, "Invalid time format"
        booking_time = parsed_time
    
    today = get_moscow_today()
    now = get_moscow_now()
    
    # Check for past dates
    if booking_date < today:
        return False, "Cannot book past dates"
    
    # Check for too far future dates
    max_date = today + timedelta(days=max_booking_days)
    if booking_date > max_date:
        return False, f"Booking too far in future. Maximum is {max_booking_days} days"
    
    # Check for today's bookings
    if booking_date == today:
        # Parse restaurant cutoff time
        cutoff_time = parse_time_strict(restaurant_cutoff)
        if not cutoff_time:
            cutoff_time = time(18, 0)  # Default cutoff
            
        # Create datetime for booking and current time
        booking_datetime = datetime.combine(booking_date, booking_time)
        booking_datetime = to_moscow_time(booking_datetime)
        
        # Check if booking time is in past - ИСПРАВЛЕНА ЛОГИКА
        if booking_datetime < now:
            return False, "Cannot book past times"
        
        # Check cutoff time - ИСПРАВЛЕНА ЛОГИКА
        current_time_only = now.time()
        if current_time_only > cutoff_time:
            return False, "Same-day booking cutoff has passed"
    
    return True, None


def is_time_between(start_time: str, end_time: str, check_time: datetime = None) -> bool:
    """Проверка, находится ли время в указанном интервале"""
    if check_time is None:
        check_time = get_current_time()
    
    # Конвертируем строки времени в объекты времени
    start = datetime.strptime(start_time, '%H:%M').time()
    end = datetime.strptime(end_time, '%H:%M').time()
    current = check_time.time()
    
    if start <= end:
        return start <= current <= end
    else:  # Интервал переходит через полночь
        return current >= start or current <= end


def format_time_for_display(time_str: Optional[str]) -> str:
    """Safely format time string for display."""
    if not time_str or not isinstance(time_str, str):
        return ""
    
    # Basic sanitization
    clean_time = time_str.strip()[:5]
    if parse_time_strict(clean_time):
        return clean_time
    
    return ""


def get_moscow_datetime_str() -> str:
    """Get current Moscow datetime as string for logging."""
    return get_moscow_now().strftime("%Y-%m-%d %H:%M:%S %Z")


def get_local_datetime_str() -> str:
    """Get current local datetime as string for logging."""
    return get_current_time().strftime("%Y-%m-%d %H:%M:%S %Z")


def get_booking_time_limits(restaurant_cutoff: str = "18:00") -> dict:
    """
    Get booking time limits for API responses.
    """
    today = get_moscow_today()
    now = get_moscow_now()
    
    cutoff_time = parse_time_strict(restaurant_cutoff) or time(18, 0)
    
    return {
        "current_time": now.isoformat(),
        "today": today.isoformat(),
        "same_day_cutoff": cutoff_time.strftime("%H:%M"),
        "cutoff_passed": now.time() > cutoff_time,
        "max_booking_days": MAX_BOOKING_DAYS
    }


def calculate_age(birth_date: Union[date, str], reference_date: Optional[date] = None) -> Optional[int]:
    """
    Safely calculate age from birth date.
    Returns None for invalid dates or future birth dates.
    """
    if isinstance(birth_date, str):
        birth_date = strict_parse_date(birth_date)
        if not birth_date:
            return None
    
    if not reference_date:
        reference_date = get_moscow_today()
    
    if birth_date > reference_date:
        return None  # Future birth date
    
    age = reference_date.year - birth_date.year
    # Adjust for birthday not yet occurred this year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        age -= 1
    
    return age


def get_next_slot_initialization_time() -> datetime:
    """
    Calculate next slot initialization time based on configuration.
    Used by background tasks.
    """
    local_tz = get_local_timezone()
    now_local = get_current_time()
    
    # Запускаем в указанное в конфигах время
    initialization_hour = getattr(settings, 'SLOT_INITIALIZATION_HOUR', 2)
    target_time_local = now_local.replace(
        hour=initialization_hour,
        minute=1,
        second=0,
        microsecond=0
    ) + timedelta(days=1)
    
    # Если уже прошло время на сегодня, запускаем завтра
    if now_local >= target_time_local.replace(day=now_local.day):
        target_time_local += timedelta(days=1)
    
    return target_time_local


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


# Deprecation warnings for less secure functions
def deprecated_parse_date_to_moscow(date_str: str) -> Optional[date]:
    """
    Deprecated: Use strict_parse_date instead for better security.
    """
    import warnings
    warnings.warn(
        "parse_date_to_moscow is deprecated. Use strict_parse_date for better security.",
        DeprecationWarning,
        stacklevel=2
    )
    return parse_date_to_moscow(date_str)