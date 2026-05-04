#!/usr/bin/env python3
"""
Утилита для проверки и установки webhook
"""
import asyncio
import os
import sys
from telegram import Bot

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN environment variable is not set!")
    sys.exit(1)

WEBHOOK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL", "https://pticasinicafamily.ru/webhook/public")


async def check_webhook():
    """Проверить текущие настройки webhook"""
    bot = Bot(TELEGRAM_BOT_TOKEN)
    
    print("🔍 Checking webhook info...")
    webhook_info = await bot.get_webhook_info()
    
    print(f"\n📊 Current webhook status:")
    print(f"  URL: {webhook_info.url}")
    print(f"  Pending updates: {webhook_info.pending_update_count}")
    print(f"  Max connections: {webhook_info.max_connections}")
    print(f"  Allowed updates: {webhook_info.allowed_updates}")
    
    if webhook_info.last_error_date:
        print(f"\n⚠️  Last error:")
        print(f"  Date: {webhook_info.last_error_date}")
        print(f"  Message: {webhook_info.last_error_message}")
    
    return webhook_info


async def set_webhook():
    """Установить webhook"""
    bot = Bot(TELEGRAM_BOT_TOKEN)
    
    print(f"\n🔧 Setting webhook to: {WEBHOOK_URL}")
    result = await bot.set_webhook(
        url=WEBHOOK_URL,
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True
    )
    
    if result:
        print("✅ Webhook set successfully!")
    else:
        print("❌ Failed to set webhook")
    
    return result


async def delete_webhook():
    """Удалить webhook"""
    bot = Bot(TELEGRAM_BOT_TOKEN)
    
    print("\n🗑️  Deleting webhook...")
    result = await bot.delete_webhook(drop_pending_updates=True)
    
    if result:
        print("✅ Webhook deleted successfully!")
    else:
        print("❌ Failed to delete webhook")
    
    return result


async def main():
    """Главная функция"""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python check_webhook.py check   # Check current webhook")
        print("  python check_webhook.py set     # Set webhook")
        print("  python check_webhook.py delete  # Delete webhook")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "check":
        await check_webhook()
    elif command == "set":
        await set_webhook()
        await check_webhook()
    elif command == "delete":
        await delete_webhook()
        await check_webhook()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
