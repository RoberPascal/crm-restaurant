import os
import sys
import secrets
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.append(str(Path(__file__).parent.parent))

# Импортируем СИНХРОННЫЕ инструменты для скриптов
from app.db.session import SyncScriptSessionLocal, sync_engine
from app.db.models.user import User, Base
from app.db.models.user_public import UserPublic  # ensure mapper is loaded for Booking.user_public
from app.db.models.restaurant import Restaurant
from app.db.models.user_restaurant import user_restaurant
from app.db.models.slot import TimeSlot
from app.db.models.table import Table
from app.db.models.booking import Booking

def init_admin():
    """Создаёт первого администратора, если пользователей нет"""
    db = SyncScriptSessionLocal()
    
    try:
        # Создаём таблицы (если не существуют)
        print("🔄 Создание таблиц...")
        Base.metadata.create_all(bind=sync_engine)
        print("✅ Таблицы созданы")
        
        # Проверяем, есть ли пользователи
        user_count = db.query(User).count()
        if user_count > 0:
            print("✅ Пользователи уже существуют. Инициализация не требуется.")
            return
        
        # Генерируем безопасный пароль
        username = "admin"
        password = secrets.token_urlsafe(12)
        
        # Создаём админа
        admin_user = User(
            username=username,
            hashed_password=User.hash_password(password),
            role="admin",
            is_active=True
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        # Сохраняем учётные данные
        credentials_file = Path("admin-credentials.txt")
        with open(credentials_file, "w", encoding="utf-8") as f:
            f.write(f"Логин: {username}\n")
            f.write(f"Пароль: {password}\n")
            f.write(f"\n⚠️ СОХРАНИТЕ ЭТИ ДАННЫЕ! Пароль больше не будет показан.\n")
        
        print(f"\n🎉 Администратор создан!")
        print(f"   Логин: {username}")
        print(f"   Пароль: {password}")
        print(f"\n📄 Учётные данные сохранены в: {credentials_file.absolute()}")
        print(f"   ⚠️  НЕ ЗАГРУЖАЙТЕ ЭТОТ ФАЙЛ В GIT!")
        
    except Exception as e:
        print(f"❌ Ошибка при инициализации: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    init_admin()