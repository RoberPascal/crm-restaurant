# Telegram Bot - Staff (Бот для персонала)

Telegram бот для уведомлений персонала ресторана о бронированиях.

## Функционал

- 🔔 Уведомления о новых бронированиях
- ⏰ Напоминания о заканчивающихся бронях
- 📊 Статистика по бронированиям
- 🪑 Уведомления о назначении столов
- ❌ Уведомления об отменах

## Установка и запуск

### Локальная разработка

```bash
pip install -r requirements.txt
python bot.py
```

### Docker

```bash
docker-compose up -d telegram-bot-staff
```

## Конфигурация

Создайте файл `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_STAFF_CHAT_ID=your_staff_chat_id
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname
ENVIRONMENT=development
```

## Структура проекта

```
telegram-bot-staff/
├── bot.py              # Основной файл бота
├── config.py           # Конфигурация
├── handlers/           # Обработчики команд
├── services/           # Сервисы (Redis, БД, уведомления)
├── utils/              # Утилиты
├── Dockerfile          # Docker образ
├── requirements.txt    # Зависимости
└── README.md           # Документация
```

