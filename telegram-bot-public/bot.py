#!/usr/bin/env python3
# bot.py
"""
Публичный Telegram бот для пользователей ресторана
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import json
import structlog

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
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
    try:
        user = update.effective_user
        if not user:
            logger.warning("Start command without user")
            return
        
        logger.info("Start command received", user_id=user.id, username=user.username)

        first_name = user.first_name or "друг"
        welcome_text = (
            f"Здравствуйте, {first_name}! 👋\n"
            "Добро пожаловать в личного консьержа — здесь вы можете быстро забронировать стол, посмотреть меню и узнать о наших ресторанах. Всё просто и удобно — в один клик.\n\n"
            "Чтобы начать — нажмите «Открыть приложение».\n\n"
            "С нетерпением ждём встречи в наших ресторанах!"
        )

        # Кнопка открытия веб‑приложения, если указан URL
        keyboard_rows = []
        if settings.TELEGRAM_WEBAPP_URL:
            keyboard_rows.append([InlineKeyboardButton(
                settings.TELEGRAM_WEBAPP_TEXT or "Открыть приложение", 
                web_app=WebAppInfo(url=settings.TELEGRAM_WEBAPP_URL)
            )])
        else:
            # Запасной вариант — простое меню
            keyboard_rows.extend([
                [InlineKeyboardButton("📅 Мои бронирования", callback_data="my_bookings")],
                [InlineKeyboardButton("ℹ️ О баре", callback_data="about")],
                [InlineKeyboardButton("🎉 Акции", callback_data="promotions")]
            ])
        reply_markup = InlineKeyboardMarkup(keyboard_rows)

        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup)
    except Exception as e:
        logger.error("Error in start_command", error=str(e), exc_info=True)
        try:
            if update.effective_message:
                await update.effective_message.reply_text("😕 Произошла ошибка. Попробуйте ещё раз.")
        except Exception:
            pass


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "📋 Доступные команды:\n\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
        "/bookings - Мои бронирования\n"
        "/settings - Настройки уведомлений\n\n"
        "Я автоматически отправляю напоминания о ваших бронированиях!"
    )
    await update.message.reply_text(help_text)


async def bookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /bookings - показать бронирования пользователя"""
    user = update.effective_user
    logger.info("Bookings command received", user_id=user.id)

    try:
        # Получаем бронирования пользователя из БД
        bookings = await db_service.get_user_bookings(user.id)

        if not bookings:
            await update.message.reply_text(
                "📅 У вас пока нет активных бронирований.\n\n"
                "Забронируйте столик через наше приложение!"
            )
            return

        text = "📅 Ваши бронирования:\n\n"
        for booking in bookings[:10]:  # Показываем максимум 10
            # Используем start_datetime вместо отдельных date/time
            start_datetime = booking.get('start_datetime')
            if start_datetime:
                try:
                    dt = datetime.fromisoformat(start_datetime)
                    date_str = dt.strftime("%d.%m.%Y")
                    time_str = dt.strftime("%H:%M")
                except (ValueError, TypeError):
                    date_str = booking.get('date', 'Не указана')
                    time_str = booking.get('time', 'Не указано')
            else:
                # fallback на старые поля если есть
                date_str = booking.get('date', 'Не указана')
                time_str = booking.get('time', 'Не указано')

            restaurant = booking.get('restaurant_name', 'Бар')
            status = booking.get('status', 'pending')

            # Форматируем статус для красоты
            status_labels = {
                'pending': 'Ожидает подтверждения',
                'pending_review': 'На проверке',
                'confirmed': 'Подтверждено',
                'assigned': 'Стол назначен',
                'arrived': 'Гости прибыли',
                'completed': 'Завершено',
                'cancelled': 'Отменено',
                'no_show': 'Неявка'
            }
            status_display = status_labels.get(status, status)

            text += f"{restaurant}\n"
            text += f"{date_str} в {time_str}\n"
            text += f"{booking['adults'] + booking.get('children', 0)} гостей\n"
            text += f"{status_display}\n"

            # Добавляем номер стола если есть
            table_number = booking.get('table_number')
            if table_number:
                text += f"Стол: №{table_number}\n"

            text += "\n"

        await update.message.reply_text(text)

    except Exception as e:
        logger.error("Error fetching bookings", error=str(e), user_id=user.id)
        await update.message.reply_text("❌ Не удалось загрузить бронирования. Попробуйте позже.")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /settings - настройки уведомлений"""
    user = update.effective_user

    settings_text = (
        "⚙️ Настройки уведомлений\n\n"
        "В настоящее время вы получаете:\n"
        "• Напоминания о бронированиях за 24 часа\n"
        "• Уведомления об изменении статуса\n"
        "• Информацию об акциях\n\n"
        "Настройки будут доступны в будущих обновлениях!"
    )

    await update.message.reply_text(settings_text)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    if data == "my_bookings":
        # Создаем обновление для вызова команды bookings
        fake_update = Update(
            update_id=update.update_id,
            message=query.message,
            callback_query=query
        )
        await bookings_command(fake_update, context)
    elif data == "about":
        await query.edit_message_text(
            "ℹ️ О баре Птица\n\n"
            "Мы рады видеть вас в нашем баре!\n\n"
            "📍 Адрес: уточните в приложении\n"
            "📞 Телефон: уточните в приложении\n"
            "🕐 Работаем ежедневно с 15:00 до 02:00\n\n"
            "Присоединяйтесь к нам для незабываемых вечеров!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Мои бронирования", callback_data="my_bookings")],
                [InlineKeyboardButton("🎉 Акции", callback_data="promotions")]
            ])
        )
    elif data == "promotions":
        await query.edit_message_text(
            "🎉 Специальные акции\n\n"
            "🌟 Счастливые часы:\n"
            "• С 15:00 до 18:00 - скидка 20% на все напитки\n\n"
            "🎂 День рождения:\n"
            "• Имениннику бокал шампанского в подарок\n\n"
            "👥 Большая компания:\n"
            "• От 6 человек - комплимент от шеф-повара\n\n"
            "Следите за новыми акциями в нашем приложении!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Мои бронирования", callback_data="my_bookings")],
                [InlineKeyboardButton("ℹ️ О ресторане", callback_data="about")]
            ])
        )


async def handle_booking_event(event_data: dict):
    """Обработка событий бронирований из Redis"""
    try:
        event_type = event_data.get("type")
        booking = event_data.get("booking", {})
        restaurant_slug = event_data.get("restaurant_slug")

        logger.info("Processing booking event", event_type=event_type, booking_id=booking.get('id'))

        if event_type == "booking_created":
            await notification_service.send_booking_confirmation(booking, restaurant_slug)
        elif event_type == "booking_updated":
            await notification_service.send_booking_update(booking, restaurant_slug)
        elif event_type == "booking_deleted":
            await notification_service.send_booking_cancellation(booking, restaurant_slug)
        elif event_type == "booking_cancelled":
            await notification_service.send_booking_cancellation(booking, restaurant_slug)

    except Exception as e:
        logger.error("Error handling booking event", error=str(e), event=event_data)


async def check_upcoming_bookings():
    """Проверка предстоящих бронирований и отправка напоминаний"""
    while True:
        try:
            await asyncio.sleep(60)  # Проверяем каждую минуту

            # Получаем все активные бронирования
            upcoming_bookings = await db_service.get_upcoming_bookings(
                hours_ahead=settings.REMINDER_BEFORE_BOOKING_HOURS
            )

            logger.debug(f"Found {len(upcoming_bookings)} upcoming bookings for reminders")

            for booking in upcoming_bookings:
                await notification_service.send_reminder(booking)

        except Exception as e:
            logger.error("Error checking upcoming bookings", error=str(e))
            await asyncio.sleep(60)


async def check_ending_bookings():
    """Проверка завершающихся бронирований (дополнительная функция)"""
    while True:
        try:
            await asyncio.sleep(300)  # Проверяем каждые 5 минут

            # Получаем завершающиеся бронирования
            ending_bookings = await db_service.get_ending_bookings()

            if ending_bookings:
                logger.info(f"Found {len(ending_bookings)} ending bookings")
                # Здесь можно добавить логику для уведомлений о завершении

        except Exception as e:
            logger.error("Error checking ending bookings", error=str(e))
            await asyncio.sleep(300)


async def post_init(application: Application):
    """Инициализация после запуска бота"""
    global db_service, notification_service, redis_listener

    logger.info("Initializing services...", environment=settings.ENVIRONMENT)

    try:
        # Проверка токена бота
        bot_info = await application.bot.get_me()
        logger.info("Bot authenticated", bot_username=bot_info.username, bot_id=bot_info.id)

        # Инициализация сервисов
        db_service = DatabaseService(settings.DATABASE_URL)
        await db_service.initialize()
        logger.info("Database service initialized")

        notification_service = NotificationService(application.bot, db_service)
        logger.info("Notification service initialized")

        # Запуск Redis listener
        redis_listener = RedisListener(
            redis_url=settings.REDIS_URL,
            channel=settings.REDIS_BOOKING_CHANNEL,
            callback=handle_booking_event
        )
        await redis_listener.start()
        logger.info("Redis listener started")

        # Запуск задач проверки бронирований
        task1 = asyncio.create_task(check_upcoming_bookings())
        _background_tasks.add(task1)
        task1.add_done_callback(_background_tasks.discard)
        task2 = asyncio.create_task(check_ending_bookings())
        _background_tasks.add(task2)
        task2.add_done_callback(_background_tasks.discard)
        logger.info("Background tasks started")

        logger.info("✅ Bot initialized successfully")

    except Exception as e:
        logger.error("❌ Failed to initialize bot", error=str(e), exc_info=True)
        raise


async def post_shutdown(application: Application):
    """Очистка при остановке бота"""
    global redis_listener

    logger.info("Shutting down bot...")

    try:
        if redis_listener:
            await redis_listener.stop()

        if db_service:
            await db_service.close()

        logger.info("Bot shut down successfully")

    except Exception as e:
        logger.error("Error during bot shutdown", error=str(e))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "😕 Произошла ошибка при обработке вашего запроса. Попробуйте позже или используйте /start"
            )
    except Exception as e:
        logger.error("Failed to send error message to user", error=str(e))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    message_text = update.message.text

    logger.info("Message received", user_id=user.id, message=message_text)

    # Если сообщение не команда, отправляем подсказку
    if not message_text.startswith('/'):
        help_text = (
            "🤖 Я понимаю только команды. Используйте:\n\n"
            "/start - начать работу\n"
            "/help - справка по командам\n"
            "/bookings - мои бронирования\n"
            "/settings - настройки\n\n"
            "Или используйте кнопки меню!"
        )
        await update.message.reply_text(help_text)


async def webhook_update(request):
    """Обработчик webhook запросов с логированием"""
    logger.info("Webhook request received", 
                method=request.method,
                path=request.path,
                content_type=request.content_type)
    return await request


def main():
    """Главная функция запуска бота"""
    logger.info("Starting public Telegram bot...")

    try:
        # Создание приложения
        application = (
            Application.builder()
            .token(settings.TELEGRAM_BOT_TOKEN.get_secret_value())
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .build()
        )

        # Регистрация обработчиков
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("bookings", bookings_command))
        application.add_handler(CommandHandler("settings", settings_command))
        application.add_handler(CallbackQueryHandler(button_callback))

        # Обработчик текстовых сообщений (должен быть последним)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Глобальный обработчик ошибок
        application.add_error_handler(error_handler)

        # Запуск бота
        if settings.ENVIRONMENT == "production" and settings.TELEGRAM_WEBHOOK_URL:
            # Webhook режим для продакшена
            logger.info("Running in webhook mode",
                       webhook_url=settings.TELEGRAM_WEBHOOK_URL,
                       url_path=settings.TELEGRAM_WEBHOOK_PATH,
                       listen_port=8001)
            application.run_webhook(
                listen="0.0.0.0",
                port=8001,
                webhook_url=settings.TELEGRAM_WEBHOOK_URL,
                url_path=settings.TELEGRAM_WEBHOOK_PATH,
                secret_token=settings.TELEGRAM_WEBHOOK_SECRET or None,
                drop_pending_updates=True
            )
        else:
            # Polling режим для разработки
            logger.info("Running in polling mode")
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )

    except Exception as e:
        logger.error("Failed to start bot", error=str(e))
        raise


if __name__ == "__main__":
    main()