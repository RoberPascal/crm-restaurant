# app/services/booking_logic.py
"""
НОВАЯ логика расчёта доступных времён окончания бронирования.

Ключевые изменения:
- Работаем с datetime, а не с time → корректно обрабатываем переход через полночь
- end_datetime = None означает "до закрытия"
- Учитываем реальные интервалы броней [start_datetime, end_datetime)
- Полная поддержка ресторанов, работающих до 04:00–06:00
"""

from datetime import datetime, timedelta
from typing import List, Optional
import structlog

logger = structlog.get_logger(__name__)

# Константы
BOOKING_MIN_DURATION_MINUTES = 105      # 1ч 45мин
BUFFER_BETWEEN_BOOKINGS_MINUTES = 15    # буфер на уборку


def get_available_end_times(
    start_datetime: datetime,
    existing_bookings: List["Booking"],
    closing_datetime: datetime,
) -> List[datetime]:
    """
    Возвращает список возможных datetime окончания брони.
    """
    logger.info(
        "get_available_end_times called",
        start=start_datetime.strftime("%Y-%m-%d %H:%M"),
        closing=closing_datetime.strftime("%Y-%m-%d %H:%M"),
        bookings_count=len(existing_bookings),
    )

    min_end = start_datetime + timedelta(minutes=BOOKING_MIN_DURATION_MINUTES)

    # Ищем брони, которые пересекаются с нашим временным окном
    conflicting_bookings = []
    for booking in existing_bookings:
        # Определяем конец брони
        booking_end = booking.end_datetime or closing_datetime
        
        # Проверяем пересечение с нашим окном [start_datetime, closing_datetime]
        if (booking.start_datetime < closing_datetime and 
            booking_end > start_datetime):
            conflicting_bookings.append(booking)

    # Если нет конфликтующих броней - можно до закрытия
    if not conflicting_bookings:
        logger.info("No conflicting bookings - available till closing")
        return []

    # Ищем ближайшую бронь после нашего начала
    future_bookings = [
        b for b in conflicting_bookings 
        if b.start_datetime > start_datetime
    ]

    # Если нет броней после нас - можно до закрытия
    if not future_bookings:
        logger.info("No future bookings - available till closing")
        return []

    # Ближайшая бронь → максимальное окончание = её начало - буфер
    nearest = min(future_bookings, key=lambda b: b.start_datetime)
    max_allowed_end = nearest.start_datetime - timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)

    # Если даже минимальная длительность не влезает
    if max_allowed_end < min_end:
        logger.warning("Min duration doesn't fit before next booking")
        return []

    # Ограничиваем максимальное время закрытием
    if max_allowed_end > closing_datetime:
        max_allowed_end = closing_datetime

    # Генерируем варианты с 15-минутным шагом
    candidates = []
    current = min_end.replace(second=0, microsecond=0)
    step = timedelta(minutes=15)

    while current <= max_allowed_end:
        # Округляем до 15-минутного шага
        minutes = current.minute
        rounded_minutes = (minutes // 15) * 15
        rounded = current.replace(minute=rounded_minutes, second=0, microsecond=0)

        if rounded >= min_end and rounded <= max_allowed_end:
            candidates.append(rounded)
        
        current += step

    # Убираем дубли и сортируем
    result = sorted(set(candidates))

    logger.info(
        "Available end times calculated",
        count=len(result),
        times=[t.strftime("%H:%M") for t in result],
        max_allowed=max_allowed_end.strftime("%H:%M"),
    )

    return result

def is_booking_range_conflicting(
    new_start: datetime,
    new_end: Optional[datetime],
    existing_bookings: List["Booking"],
    buffer_minutes: int = BUFFER_BETWEEN_BOOKINGS_MINUTES,
) -> bool:
    """
    Проверяет, пересекается ли новая бронь с существующими (с учётом буфера).
    Используется при валидации админских броней с фиксированным концом.
    """
    if new_end is None:
        new_end = new_start + timedelta(hours=10)  # условно "до закрытия"

    for b in existing_bookings:
        if b.table_id is None:
            continue  # не назначенные не блокируют стол

        b_start = b.start_datetime
        b_end = b.end_datetime or (b_start + timedelta(hours=10))

        # Добавляем буфер
        b_start_buffered = b_start - timedelta(minutes=buffer_minutes)
        b_end_buffered = b_end + timedelta(minutes=buffer_minutes)

        if new_start < b_end_buffered and (new_end or new_start) > b_start_buffered:
            return True
    return False


def validate_booking_duration(
    start_datetime: datetime,
    end_datetime: Optional[datetime],
) -> tuple[bool, str]:
    """
    Проверка минимальной длительности.
    """
    if end_datetime is None:
        return True, ""

    duration = (end_datetime - start_datetime).total_seconds() / 60
    if duration < BOOKING_MIN_DURATION_MINUTES:
        return False, f"Минимальная длительность — {BOOKING_MIN_DURATION_MINUTES} минут"
    return True, ""