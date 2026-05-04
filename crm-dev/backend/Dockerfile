FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копирование зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY . .

# Переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

# Порт приложения
EXPOSE 8000

# Health check — ИСПРАВЛЕНО: используем curl (не requests), localhost, один слеш
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Запуск приложения
# ВАЖНО: workers=1, потому что WebSocket соединения хранятся in-memory,
# а background tasks (Redis listener, Strapi sync, slot init) нельзя дублировать.
# Масштабирование — через дополнительные контейнер-реплики за LB с sticky sessions.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "1000", "--limit-max-requests", "50000", "--timeout-keep-alive", "65"]
