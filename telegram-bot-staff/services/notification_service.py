# services/notification_service.py
"""
Сервис для отправки уведомлений персоналу
"""
from datetime import datetime, timezone
from typing import Dict, Optional
import structlog
from telegram import Bot
from telegram.error import TelegramError
from config import settings
import redis.asyncio as redis

logger = structlog.get_logger(__name__)


class NotificationService:
    """Сервис уведомлений для персонала"""

    def __init__(self, bot: Bot, db_service, staff_chat_id: int):
        self.bot = bot
        self.db_service = db_service
        self.staff_chat_id = staff_chat_id
        self.sent_ending_reminders: dict = {}  # {booking_id: timestamp} for TTL-based eviction
        self._redis: Optional[redis.Redis] = None
        try:
            if settings.REDIS_URL:
                self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            self._redis = None

    def _format_datetime(self, booking: Dict) -> tuple:
        """Форматирует дату и время из бронирования в формате '3 декабря 2025'"""
        months = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря"
        ]

        def format_date_ymd(ymd: str) -> str:
            try:
                parts = ymd.split("-")
                if len(parts) == 3:
                    y, m, d = map(int, parts)
                    return f"{int(d)} {months[m-1]} {y}"
            except Exception:
                pass
            return ymd

        date_str = booking.get('date') or ''
        time_str = booking.get('time') or ''
        end_time_str = booking.get('end_time') or ''

        start_dt = booking.get('start_datetime')
        end_dt = booking.get('end_datetime')

        if start_dt:
            try:
                dt = datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
                date_str = f"{dt.day} {months[dt.month-1]} {dt.year}"
                time_str = dt.strftime("%H:%M")
            except Exception:
                pass
        else:
            if isinstance(date_str, str):
                date_str = format_date_ymd(date_str)

        if end_dt:
            try:
                edt = datetime.fromisoformat(end_dt.replace('Z', '+00:00'))
                end_time_str = edt.strftime("%H:%M")
            except Exception:
                pass

        return (date_str, time_str, end_time_str)

    def _status_ru(self, status_code: str) -> str:
        mapping = {
            'pending': 'Ожидает подтверждения',
            'pending_review': 'На проверке',
            'confirmed': 'Подтверждено',
            'assigned': 'Назначен стол',
            'arrived': 'Прибыл',
            'completed': 'Завершено',
            'cancelled': 'Отменено',
            'no_show': 'Не пришёл',
        }
        return mapping.get((status_code or '').lower(), status_code or '')

    async def _already_sent(self, key: str, ttl_seconds: int = 300) -> bool:
        """Проверить/пометить событие как отправленное (идемпотентность). Возвращает True, если уже отправляли."""
        try:
            if self._redis:
                was_set = await self._redis.set(name=key, value="1", nx=True, ex=ttl_seconds)
                return not bool(was_set)
        except Exception:
            pass
        if not hasattr(self, "_mem_keys"):
            self._mem_keys = {}
        from time import time as _now
        now = _now()
        self._mem_keys = {k: v for k, v in self._mem_keys.items() if now - v < ttl_seconds}
        if key in self._mem_keys:
            return True
        self._mem_keys[key] = now
        return False

    def _format_end_time(self, booking: Dict) -> str:
        """Форматирует время окончания"""
        end_datetime = booking.get('end_datetime')
        if end_datetime:
            try:
                dt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
                return dt.strftime("%H:%M")
            except (ValueError, TypeError):
                pass
        return booking.get('end_time', '')

    async def _resolve_restaurant_name(self, booking: Dict, restaurant_slug: Optional[str] = None) -> str:
        """Пытается определить корректное название ресторана для сообщения."""
        name = booking.get('restaurant_name')
        if name and name.strip() and name.strip().lower() not in ('ресторан', 'бар'):
            return name
        # Если в событии нет имени, пробуем достать по ID брони из БД
        b_id = booking.get('id')
        if b_id and self.db_service:
            try:
                full = await self.db_service.get_booking_by_id(b_id)
                if full and full.get('restaurant_name'):
                    return full['restaurant_name']
            except Exception:
                pass
        return 'Бар'

    async def send_new_booking_alert(self, booking: Dict, restaurant_slug: str):
        """Отправить уведомление о новом бронировании"""
        try:
            # Dedupe на случай повторной публикации одного события
            b_id = booking.get('id')
            if b_id is not None and await self._already_sent(f"staff:booking_created:{b_id}", ttl_seconds=600):
                logger.info("Skip duplicate staff booking_created", booking_id=b_id)
                return

            date_str, time_start, time_end = self._format_datetime(booking)
            restaurant_name = await self._resolve_restaurant_name(booking, restaurant_slug)

            text = (
                "<b>НОВОЕ БРОНИРОВАНИЕ</b>\n\n"
                f"Бар: {restaurant_name}\n"
                f"Дата: {date_str}\n"
                f"Время начала: {time_start}\n"
                f"Время окончания: {time_end or '—'}\n"
                f"Имя: {booking.get('name', '')}\n"
                f"Телефон: {booking.get('phone', '')}\n"
                f"Гостей: {booking.get('adults', 0) + booking.get('children', 0)}\n"
                f"Статус: {self._status_ru(booking.get('status', ''))}\n"
            )

            if booking.get('wishes'):
                text += f"Пожелания: {booking.get('wishes')}\n"

            text += f"\nID: {booking.get('id', '')}"

            await self.bot.send_message(
                chat_id=self.staff_chat_id,
                text=text,
                parse_mode='HTML'
            )
            logger.info("New booking alert sent", booking_id=booking.get('id'))

        except TelegramError as e:
            logger.warning("Failed to send new booking alert", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending new booking alert", error=str(e), booking_id=booking.get('id'))

    async def send_booking_update_alert(self, booking: Dict, restaurant_slug: str):
        """Отправить уведомление об изменении бронирования"""
        try:
            status = booking.get('status', '')
            status_emoji = {
                'pending': '⏳',
                'pending_review': '📋',
                'confirmed': '✅',
                'assigned': '🪑',
                'arrived': '👋',
                'completed': '✅',
                'cancelled': '❌',
                'no_show': '🚫'
            }
            emoji = status_emoji.get(status, '📊')

            date_str, time_start, time_end = self._format_datetime(booking)

            text = (
                f"<b>ОБНОВЛЕНИЕ БРОНИРОВАНИЯ</b>\n\n"
                f"ID: {booking.get('id', '')}\n"
                f"Бар: {booking.get('restaurant_name', 'Бар')}\n"
                f"Дата: {date_str}\n"
                f"Время начала: {time_start}\n"
                f"Время окончания: {time_end or '—'}\n"
                f"Имя: {booking.get('name', '')}\n"
                f"Статус: <b>{self._status_ru(status)}</b>\n"
            )

            if booking.get('table_number'):
                text += f"Стол: №{booking.get('table_number')}\n"

            await self.bot.send_message(
                chat_id=self.staff_chat_id,
                text=text,
                parse_mode='HTML'
            )
            logger.info("Booking update alert sent", booking_id=booking.get('id'))

        except TelegramError as e:
            logger.warning("Failed to send update alert", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending update alert", error=str(e), booking_id=booking.get('id'))

    async def send_booking_deleted_alert(self, booking: Dict, restaurant_slug: str):
        """Отправить уведомление об отмене бронирования"""
        try:
            date_str, time_start, time_end = self._format_datetime(booking)
            
            cancelled_by = booking.get('cancelled_by', 'unknown')
            cancelled_by_text = "Отменено клиентом" if cancelled_by == "user" else "Отменено администратором"

            text = (
                f"<b>ОТМЕНА БРОНИРОВАНИЯ</b>\n\n"
                f"{cancelled_by_text}\n\n"
                f"ID: {booking.get('id', '')}\n"
                f"Дата: {date_str}\n"
                f"Время начала: {time_start}\n"
                f"Время окончания: {time_end or '—'}\n"
                f"Имя: {booking.get('name', '')}\n"
                f"Телефон: {booking.get('phone', '')}\n"
            )

            await self.bot.send_message(
                chat_id=self.staff_chat_id,
                text=text,
                parse_mode='HTML'
            )
            logger.info("Booking deletion alert sent", booking_id=booking.get('id'))

        except TelegramError as e:
            logger.warning("Failed to send deletion alert", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending deletion alert", error=str(e), booking_id=booking.get('id'))

    async def send_booking_delay_alert(self, booking: Dict, restaurant_slug: str):
        """Отправить уведомление об опоздании клиента"""
        try:
            date_str, time_start, time_end = self._format_datetime(booking)
            delay_minutes = booking.get('delay_minutes')
            
            text = (
                "<b>КЛИЕНТ ОПАЗДЫВАЕТ</b>\n\n"
                f"ID: {booking.get('id', '')}\n"
                f"Дата: {date_str}\n"
                f"Время начала: {time_start}\n"
                f"Имя: {booking.get('name', '')}\n"
                f"Телефон: {booking.get('phone', '')}\n"
            )
            
            if booking.get('table_number'):
                text += f"Стол: №{booking.get('table_number')}\n"
            
            if delay_minutes:
                text += f"\nОпоздание: ~{delay_minutes} минут"
            else:
                text += f"\nКлиент сообщил об опоздании"

            await self.bot.send_message(
                chat_id=self.staff_chat_id,
                text=text,
                parse_mode='HTML'
            )
            logger.info("Booking delay alert sent", booking_id=booking.get('id'), delay_minutes=delay_minutes)

        except TelegramError as e:
            logger.warning("Failed to send delay alert", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending delay alert", error=str(e), booking_id=booking.get('id'))

    async def send_ending_reminder(self, booking: Dict):
        """Отправить напоминание о заканчивающейся брони"""
        try:
            booking_id = booking.get('id')

            # Проверяем, не отправляли ли уже напоминание
            if booking_id in self.sent_ending_reminders:
                return

            end_datetime = booking.get('end_datetime')
            minutes_left = 0

            if end_datetime:
                try:
                    end_time = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
                    minutes_left = max(0, int((end_time - datetime.now(timezone.utc)).total_seconds() / 60))
                except (ValueError, TypeError):
                    pass

            date_str, time_str, end_time_str = self._format_datetime(booking)

            text = (
                "<b>НАПОМИНАНИЕ: Бронирование скоро закончится</b>\n\n"
                f"ID: {booking_id}\n"
                f"Бар: {booking.get('restaurant_name', 'Бар')}\n"
                f"Дата: {date_str}\n"
                f"Начало: {time_str}\n"
                f"Имя: {booking.get('name', '')}\n"
                f"Стол: №{booking.get('table_number', 'не назначен')}\n"
                f"Осталось: ~{minutes_left} минут\n"
            )

            await self.bot.send_message(
                chat_id=self.staff_chat_id,
                text=text,
                parse_mode='HTML'
            )

            # Помечаем как отправленное с timestamp для TTL-based eviction
            from time import time as _now
            now = _now()
            self.sent_ending_reminders[booking_id] = now

            # Удаляем записи старше 2 часов вместо полного сброса
            self.sent_ending_reminders = {
                k: v for k, v in self.sent_ending_reminders.items()
                if now - v < 7200
            }

            logger.info("Ending reminder sent", booking_id=booking_id, minutes_left=minutes_left)

        except TelegramError as e:
            logger.warning("Failed to send ending reminder", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending ending reminder", error=str(e), booking_id=booking.get('id'))