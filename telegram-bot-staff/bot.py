#!/usr/bin/env python3
"""
Telegram бот для уведомлений персонала ресторана
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import json
import structlog

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from config import settings
from services.redis_listener import RedisListener
from services.database import DatabaseService
from services.notification_service import NotificationService
from utils.logging_config import setup_logging

# Настройка логирования
setup_logging(settings.LOG_LEVEL)
logger = structlog.get_logger(__name__)

# Глобальные сервисы
db_service: Optional[DatabaseService] = None
notification_service: Optional[NotificationService] = None
redis_listener: Optional[RedisListener] = None
_background_tasks: set = set()  # Храним ссылки на фоновые задачи


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    logger.info("Start command received", user_id=user.id, username=user.username)

    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для персонала бара Птица.\n"
        "Я отправляю уведомления о:\n"
        "🔔 Новых бронированиях\n"
        "⏰ Заканчивающихся бронях\n"
        "🪑 Назначении столов\n"
        "❌ Отменах бронирований\n\n"
        "Используйте /help для списка команд"
    )

    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📋 Доступные команды:\n\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
        "/stats - Статистика по бронированиям\n"
        "/today - Бронирования на сегодня\n"
        "/booking <id> - Информация о бронировании\n"
    )
    await update.message.reply_text(help_text)


async def _check_staff_access(update: Update) -> bool:
    """Проверяет, что команда вызвана из авторизованного чата персонала"""
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id != settings.TELEGRAM_STAFF_CHAT_ID:
        logger.warning("Unauthorized access attempt", chat_id=chat_id, user_id=update.effective_user.id if update.effective_user else None)
        if update.message:
            await update.message.reply_text("⛔ Доступ запрещён. Эта команда доступна только для персонала.")
        return False
    return True


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats - статистика"""
    if not await _check_staff_access(update):
        return
    try:
        stats = await db_service.get_today_stats()

        status_labels = {
            'pending': '⏳ Ожидают',
            'pending_review': '📋 На проверке',
            'confirmed': '✅ Подтверждено',
            'assigned': '🪑 Назначено',
            'arrived': '👋 Прибыли',
            'completed': '✅ Завершено',
            'cancelled': '❌ Отменено',
            'no_show': '🚫 Неявки'
        }

        text = "📊 Статистика на сегодня\n\n"
        for status, label in status_labels.items():
            count = stats.get(status, 0)
            if count > 0:
                text += f"{label}: {count}\n"

        total = sum(stats.values())
        text += f"\n📈 Всего: {total} бронирований"

        await update.message.reply_text(text)
    except Exception as e:
        logger.error("Error getting stats", error=str(e))
        await update.message.reply_text("❌ Не удалось получить статистику")


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /today - бронирования на сегодня"""
    if not await _check_staff_access(update):
        return
    try:
        bookings = await db_service.get_today_bookings()

        if not bookings:
            await update.message.reply_text("📅 На сегодня нет бронирований")
            return

        text = "📅 Бронирования на сегодня:\n\n"
        for booking in bookings[:15]:  # Максимум 15
            time_str = booking.get('time', '')
            name = booking.get('name', '')
            guests = booking.get('adults', 0) + booking.get('children', 0)
            status = booking.get('status', '')
            table = booking.get('table_number', 'не назначен')
            restaurant = booking.get('restaurant_name', '')

            status_emoji = {
                'pending': '⏳',
                'pending_review': '📋',
                'confirmed': '✅',
                'assigned': '🪑',
                'arrived': '👋',
                'completed': '✅',
                'cancelled': '❌'
            }
            emoji = status_emoji.get(status, '📊')

            text += f"{time_str} - {name} ({guests} чел.)\n"
            text += f"   {restaurant}, Стол: {table}\n\n"

        if len(bookings) > 15:
            text += f"... и еще {len(bookings) - 15} бронирований"

        await update.message.reply_text(text)
    except Exception as e:
        logger.error("Error getting today bookings", error=str(e))
        await update.message.reply_text("❌ Не удалось загрузить бронирования")


async def booking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /booking <id> - информация о бронировании"""
    if not await _check_staff_access(update):
        return
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите ID бронирования: /booking <id>")
            return

        booking_id = context.args[0]
        if not booking_id.isdigit():
            await update.message.reply_text("❌ ID бронирования должен быть числом")
            return

        booking = await db_service.get_booking_by_id(int(booking_id))
        if not booking:
            await update.message.reply_text("❌ Бронирование не найдено")
            return

        date_str, time_str, end_time_str = notification_service._format_datetime(booking)

        text = (
            f"<b>Информация о бронировании #{booking_id}</b>\n\n"
            f"Бар: {booking.get('restaurant_name', 'Бар')}\n"
            f"Дата: {date_str}\n"
            f"Время: {time_str}\n"
        )

        if end_time_str:
            text += f"Конец: {end_time_str}\n"

        text += (
            f"Имя: {booking.get('name', '')}\n"
            f"Телефон: {booking.get('phone', '')}\n"
            f"Гостей: {booking.get('adults', 0)} взрослых, {booking.get('children', 0)} детей\n"
            f"Статус: {booking.get('status', '')}\n"
            f"Стол: №{booking.get('table_number', 'не назначен')}\n"
        )

        if booking.get('wishes'):
            text += f"Пожелания: {booking.get('wishes')}\n"

        await update.message.reply_text(text, parse_mode='HTML')

    except Exception as e:
        logger.error("Error getting booking info", error=str(e))
        await update.message.reply_text("❌ Не удалось получить информацию о бронировании")


async def handle_booking_event(event_data: dict):
    """Обработка событий бронирований из Redis"""
    try:
        event_type = event_data.get("type")
        booking = event_data.get("booking", {})
        restaurant_slug = event_data.get("restaurant_slug")

        logger.info("Processing booking event", event_type=event_type, booking_id=booking.get('id'))

        if event_type == "booking_created":
            await notification_service.send_new_booking_alert(booking, restaurant_slug)
        elif event_type == "booking_updated":
            await notification_service.send_booking_update_alert(booking, restaurant_slug)
        elif event_type in ["booking_deleted", "booking_cancelled"]:
            await notification_service.send_booking_deleted_alert(booking, restaurant_slug)
        elif event_type == "booking_delay":
            await notification_service.send_booking_delay_alert(booking, restaurant_slug)

    except Exception as e:
        logger.error("Error handling booking event", error=str(e), event=event_data)


async def check_ending_bookings():
    """Проверка заканчивающихся бронирований и отправка напоминаний"""
    while True:
        try:
            await asyncio.sleep(60)  # Проверяем каждую минуту

            # Получаем бронирования, которые скоро закончатся
            ending_bookings = await db_service.get_ending_bookings(minutes_ahead=30)

            logger.debug(f"Found {len(ending_bookings)} ending bookings")

            for booking in ending_bookings:
                await notification_service.send_ending_reminder(booking)

        except Exception as e:
            logger.error("Error checking ending bookings", error=str(e))
            await asyncio.sleep(60)


async def post_init(application: Application):
    """Инициализация после запуска бота"""
    global db_service, notification_service, redis_listener

    logger.info("Initializing staff bot services...")

    try:
        # Инициализация сервисов
        db_service = DatabaseService(settings.DATABASE_URL)
        await db_service.initialize()

        notification_service = NotificationService(
            application.bot,
            db_service,
            staff_chat_id=settings.TELEGRAM_STAFF_CHAT_ID
        )

        # Запуск Redis listener
        redis_listener = RedisListener(
            redis_url=settings.REDIS_URL,
            channel=settings.REDIS_BOOKING_CHANNEL,
            callback=handle_booking_event
        )
        await redis_listener.start()

        # Запуск задачи проверки заканчивающихся бронирований
        task = asyncio.create_task(check_ending_bookings())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        logger.info("Staff bot initialized successfully")

    except Exception as e:
        logger.error("Failed to initialize staff bot", error=str(e))
        raise


async def post_shutdown(application: Application):
    """Очистка при остановке бота"""
    global redis_listener

    logger.info("Shutting down staff bot...")

    try:
        if redis_listener:
            await redis_listener.stop()

        if db_service:
            await db_service.close()

        logger.info("Staff bot shut down successfully")

    except Exception as e:
        logger.error("Error during staff bot shutdown", error=str(e))


def main():
    """Главная функция запуска бота"""
    logger.info("Starting staff Telegram bot...")

    try:
        # Создание приложения
        application = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_STAFF_TOKEN.get_secret_value())
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .build()
        )

        # Регистрация обработчиков
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("today", today_command))
        application.add_handler(CommandHandler("booking", booking_command))

        # Глобальный обработчик ошибок
        async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
            logger.error("Exception while handling an update:", exc_info=context.error)
            try:
                if isinstance(update, Update) and update.effective_message:
                    await update.effective_message.reply_text("❌ Произошла ошибка. Попробуйте позже.")
            except Exception:
                pass
        application.add_error_handler(error_handler)

        # Запуск бота
        if settings.ENVIRONMENT == "production" and getattr(settings, 'TELEGRAM_BOT_STAFF_WEBHOOK_URL', None):
            # Webhook режим для продакшена
            application.run_webhook(
                listen="0.0.0.0",
                port=8002,
                webhook_url=settings.TELEGRAM_BOT_STAFF_WEBHOOK_URL,
                url_path=getattr(settings, 'TELEGRAM_WEBHOOK_PATH', '/'),
                secret_token=getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', None) or None,
            )
        else:
            # Polling режим для разработки
            logger.info("Running staff bot in polling mode")
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )

    except Exception as e:
        logger.error("Failed to start staff bot", error=str(e))
        raise


if __name__ == "__main__":
    main()