# services/notification_service.py
"""
Сервис для отправки уведомлений пользователям
"""
from datetime import datetime, timedelta
from typing import Dict, Optional
import structlog
from telegram import Bot
from telegram.error import TelegramError

from services.database import DatabaseService
from config import settings
import redis.asyncio as redis

logger = structlog.get_logger(__name__)


class NotificationService:
    """Сервис уведомлений"""
    
    def __init__(self, bot: Bot, db_service: DatabaseService):
        self.bot = bot
        self.db_service = db_service
        self.sent_reminders = {}  # {key: timestamp} for TTL-based eviction
        # Клиент Redis для идемпотентности (дедупликация)
        self._redis: Optional[redis.Redis] = None
        try:
            if settings.REDIS_URL:
                self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            self._redis = None
    
    async def _already_sent(self, key: str, ttl_seconds: int = 300) -> bool:
        """Проверить/пометить событие как отправленное (идемпотентность). Возвращает True, если уже отправляли."""
        try:
            if self._redis:
                # SET key NX EX ttl
                was_set = await self._redis.set(name=key, value="1", nx=True, ex=ttl_seconds)
                return not bool(was_set)
        except Exception:
            pass
        # Fallback в память (на случай отсутствия Redis)
        if not hasattr(self, "_mem_keys"):
            self._mem_keys = {}
        now = datetime.now().timestamp()
        # Очистка просроченных
        self._mem_keys = {k: v for k, v in self._mem_keys.items() if now - v < ttl_seconds}
        if key in self._mem_keys:
            return True
        self._mem_keys[key] = now
        return False

    async def send_booking_confirmation(self, booking: Dict, restaurant_slug: str):
        """Отправить подтверждение создания бронирования"""
        try:
            # Сначала пытаемся получить telegram_user_id напрямую из события
            telegram_user_id = booking.get('telegram_user_id')
            
            # Если нет, пытаемся получить через user_public_id
            if not telegram_user_id:
                user_public_id = booking.get('user_public_id')
                if user_public_id:
                    user = await self.db_service.get_user_by_public_id(user_public_id)
                    if user and user.get('telegram_user_id'):
                        telegram_user_id = user['telegram_user_id']
            
            # Если нет id в брони и не привязано к user_public (админская бронь) — не шлём уведомление.
            # Это предотвращает ситуации, когда по номеру телефона чужой пользователь получает сообщение.
            if not telegram_user_id and not booking.get('user_public_id'):
                logger.debug(
                    "Booking has no linked telegram/user_public; skipping notification",
                    booking_id=booking.get('id'),
                )
                return

            # Если все еще нет, пытаемся найти пользователя по телефону (только для публичных бронирований)
            if not telegram_user_id:
                user = await self.db_service.get_user_by_phone(booking.get('phone'))
                if not user or not user.get('telegram_user_id'):
                    logger.debug("No telegram_user_id found for booking", booking_id=booking.get('id'))
                    return
                telegram_user_id = user['telegram_user_id']

            # Идемпотентность: защищаемся от дублей "создано"
            b_id = booking.get('id')
            if b_id is not None:
                if await self._already_sent(f"pub:booking_created:{b_id}", ttl_seconds=600):
                    logger.info("Skip duplicate booking_created", booking_id=b_id)
                    return

            months = [
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]

            def format_date_ymd(ymd: str) -> str:
                try:
                    y, m, d = map(int, ymd.split("-"))
                    return f"{int(d)} {months[m-1]} {y}"
                except Exception:
                    return ymd

            start_datetime = booking.get('start_datetime')
            end_datetime = booking.get('end_datetime')
            date_str = booking.get('date', '')
            time_start = booking.get('time', '')
            time_end = booking.get('end_time', '')
            if start_datetime:
                try:
                    dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                    date_str = f"{dt.day} {months[dt.month - 1]} {dt.year}"
                    time_start = dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass
            else:
                if isinstance(date_str, str) and date_str:
                    date_str = format_date_ymd(date_str)
            if end_datetime:
                try:
                    edt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
                    time_end = edt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass
            
            # Resolve restaurant name (enrich from DB if missing)
            restaurant_name = booking.get('restaurant_name', 'Бар')
            if not restaurant_name or restaurant_name.strip().lower() in ('ресторан', 'бар'):
                b_id = booking.get('id')
                if b_id and self.db_service:
                    try:
                        full = await self.db_service.get_booking_by_id(b_id)
                        if full and full.get('restaurant_name'):
                            restaurant_name = full['restaurant_name']
                    except Exception:
                        pass
            
            # Проверяем, совпадает ли время конца с временем закрытия (бронь до закрытия)
            closing_time = booking.get('closing_time')
            show_end_time = time_end and (not closing_time or time_end != closing_time)
            
            time_info = f"Время начала: {time_start}\n"
            if show_end_time:
                time_info += f"Время окончания: {time_end}\n"
            
            text = (
                "Бронирование создано!\n\n"
                f"Бар: {restaurant_name}\n"
                f"Дата: {date_str}\n"
                f"{time_info}"
                f"Гостей: {booking.get('adults', 0) + booking.get('children', 0)}\n"
            )

            # Добавляем пожелания, если есть
            wishes = booking.get('wishes')
            if wishes:
                text += f"Пожелания: {wishes}\n"

            text += "\nМы напомним вам о бронировании заранее!"
            
            await self.bot.send_message(
                chat_id=telegram_user_id,
                text=text
            )
            logger.info("Booking confirmation sent", booking_id=booking.get('id'), user_id=telegram_user_id)
            
        except TelegramError as e:
            logger.warning("Failed to send booking confirmation", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending booking confirmation", error=str(e), booking_id=booking.get('id'))
    
    async def send_booking_update(self, booking: Dict, restaurant_slug: str):
        """Отправить уведомление об изменении бронирования"""
        try:
            # Находим пользователя по booking_id
            user = await self.db_service.get_user_by_booking_id(booking.get('id'))
            if not user or not user.get('telegram_user_id'):
                return
            
            def status_ru(s: str) -> str:
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
                return mapping.get((s or '').lower(), s or '')

            months = [
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]

            def format_date_ymd(ymd: str) -> str:
                try:
                    y, m, d = map(int, ymd.split("-"))
                    return f"{int(d)} {months[m-1]} {y}"
                except Exception:
                    return ymd

            start_datetime = booking.get('start_datetime')
            end_datetime = booking.get('end_datetime')
            date_str = booking.get('date', '')
            time_start = booking.get('time', '')
            time_end = booking.get('end_time', '')
            if start_datetime:
                try:
                    dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                    date_str = f"{dt.day} {months[dt.month - 1]} {dt.year}"
                    time_start = dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass
            else:
                if isinstance(date_str, str) and date_str:
                    date_str = format_date_ymd(date_str)
            if end_datetime:
                try:
                    edt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
                    time_end = edt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass
            
            # Проверяем, совпадает ли время конца с временем закрытия (бронь до закрытия)
            closing_time = booking.get('closing_time')
            show_end_time = time_end and (not closing_time or time_end != closing_time)
            
            time_info = f"Время начала: {time_start}\n"
            if show_end_time:
                time_info += f"Время окончания: {time_end}\n"
            
            text = (
                "Обновление бронирования\n\n"
                f"Бар: {booking.get('restaurant_name', 'Бар')}\n"
                f"Дата: {date_str}\n"
                f"{time_info}"
                f"Статус: {status_ru(booking.get('status',''))}\n"
            )
            
            if booking.get('table_number'):
                text += f"Стол: №{booking.get('table_number')}\n"
            
            await self.bot.send_message(
                chat_id=user['telegram_user_id'],
                text=text
            )
            logger.info("Booking update sent", booking_id=booking.get('id'))
            
        except TelegramError as e:
            logger.warning("Failed to send booking update", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending booking update", error=str(e), booking_id=booking.get('id'))
    
    async def send_booking_cancellation(self, booking: Dict, restaurant_slug: str):
        """Отправить уведомление об отмене бронирования"""
        try:
            user = await self.db_service.get_user_by_booking_id(booking.get('id'))
            if not user or not user.get('telegram_user_id'):
                return
            
            months = [
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]

            def format_date_ymd(ymd: str) -> str:
                try:
                    y, m, d = map(int, ymd.split("-"))
                    return f"{int(d)} {months[m-1]} {y}"
                except Exception:
                    return ymd

            start_datetime = booking.get('start_datetime')
            end_datetime = booking.get('end_datetime')
            date_str = booking.get('date', '')
            time_start = booking.get('time', '')
            time_end = booking.get('end_time', '')
            if start_datetime:
                try:
                    dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                    date_str = f"{dt.day} {months[dt.month - 1]} {dt.year}"
                    time_start = dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass
            else:
                if isinstance(date_str, str) and date_str:
                    date_str = format_date_ymd(date_str)
            if end_datetime:
                try:
                    edt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
                    time_end = edt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass

            # Проверяем, совпадает ли время конца с временем закрытия (бронь до закрытия)
            closing_time = booking.get('closing_time')
            show_end_time = time_end and (not closing_time or time_end != closing_time)
            
            time_info = f"Время начала: {time_start}\n"
            if show_end_time:
                time_info += f"Время окончания: {time_end}\n"
            
            text = (
                "Бронирование отменено\n\n"
                f"Дата: {date_str}\n"
                f"{time_info}\n"
                "Если у вас есть вопросы, свяжитесь с нами."
            )
            
            await self.bot.send_message(
                chat_id=user['telegram_user_id'],
                text=text
            )
            logger.info("Booking cancellation sent", booking_id=booking.get('id'))
            
        except TelegramError as e:
            logger.warning("Failed to send cancellation", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending cancellation", error=str(e), booking_id=booking.get('id'))
    
    async def send_reminder(self, booking: Dict):
        """Отправить напоминание о предстоящем бронировании"""
        try:
            booking_id = booking.get('id')
            telegram_user_id = booking.get('telegram_user_id')
            
            # Проверяем, не отправляли ли уже напоминание
            reminder_key = f"{booking_id}_{telegram_user_id}"
            if reminder_key in self.sent_reminders:
                return
            
            months = [
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]

            def format_date_ymd(ymd: str) -> str:
                try:
                    y, m, d = map(int, ymd.split("-"))
                    return f"{int(d)} {months[m-1]} {y}"
                except Exception:
                    return ymd

            start_datetime = booking.get('start_datetime')
            end_datetime = booking.get('end_datetime')
            date_str = booking.get('date', '')
            time_start = booking.get('time', '')
            time_end = booking.get('end_time', '')
            if start_datetime:
                try:
                    dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                    date_str = f"{dt.day} {months[dt.month - 1]} {dt.year}"
                    time_start = dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass
            else:
                if isinstance(date_str, str) and date_str:
                    date_str = format_date_ymd(date_str)
            if end_datetime:
                try:
                    edt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
                    time_end = edt.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass
            
            # Проверяем, совпадает ли время конца с временем закрытия (бронь до закрытия)
            closing_time = booking.get('closing_time')
            show_end_time = time_end and (not closing_time or time_end != closing_time)
            
            time_info = f"Время начала: {time_start}\n"
            if show_end_time:
                time_info += f"Время окончания: {time_end}\n"
            
            text = (
                "Напоминание о бронировании\n\n"
                f"Бар: {booking.get('restaurant_name', 'Бар')}\n"
                f"Дата: {date_str}\n"
                f"{time_info}"
                f"Гостей: {booking.get('adults', 0) + booking.get('children', 0)}\n\n"
                "Ждем вас!"
            )
            
            await self.bot.send_message(
                chat_id=telegram_user_id,
                text=text
            )
            
            # Помечаем как отправленное с TTL
            from time import time as _now
            now = _now()
            self.sent_reminders[reminder_key] = now
            
            # Удаляем записи старше 48 часов
            self.sent_reminders = {
                k: v for k, v in self.sent_reminders.items()
                if now - v < 172800
            }
            
            logger.info("Reminder sent", booking_id=booking_id, user_id=telegram_user_id)
            
        except TelegramError as e:
            logger.warning("Failed to send reminder", error=str(e), booking_id=booking.get('id'))
        except Exception as e:
            logger.error("Error sending reminder", error=str(e), booking_id=booking.get('id'))
    
    async def send_promotion(self, telegram_user_id: int, promotion_text: str):
        """Отправить информацию об акции"""
        try:
            await self.bot.send_message(
                chat_id=telegram_user_id,
                text=promotion_text,
                parse_mode='HTML'
            )
            logger.info("Promotion sent", user_id=telegram_user_id)
        except TelegramError as e:
            logger.warning("Failed to send promotion", error=str(e), user_id=telegram_user_id)

