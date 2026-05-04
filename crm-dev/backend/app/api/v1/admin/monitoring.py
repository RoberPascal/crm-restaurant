# app/api/v1/admin/monitoring.py
from fastapi import APIRouter, Depends, HTTPException
from app.core.background_tasks import get_daily_slots_stats, manual_slot_initialization
from app.core.task_monitor import task_monitor
from .deps import require_admin_role
from app.db.models.user import User

router = APIRouter()

@router.get("/monitoring/tasks", dependencies=[Depends(require_admin_role)])
async def get_task_stats():
    """Получение статистики фоновых задач"""
    return {
        "daily_slots": get_daily_slots_stats(),
        "task_monitor": task_monitor.get_status()
    }

@router.post("/monitoring/initialize-slots", dependencies=[Depends(require_admin_role)])
async def manual_initialize_slots(days_ahead: int = 1):
    """Ручная инициализация слотов"""
    if days_ahead < 0 or days_ahead > 30:
        raise HTTPException(
            status_code=400, 
            detail="days_ahead must be between 0 and 30"
        )
    
    result = await manual_slot_initialization(days_ahead)
    return result

@router.get("/monitoring/health", dependencies=[Depends(require_admin_role)])
async def get_monitoring_health():
    """Health check для мониторинга"""
    stats = get_daily_slots_stats()
    task_status = task_monitor.get_status()
    
    # Проверяем статус задач
    daily_slots_health = task_status.get("daily_slots", {}).get("status", "unknown")
    
    health_status = "healthy"
    if daily_slots_health == "unhealthy":
        health_status = "unhealthy"
    elif daily_slots_health == "degraded":
        health_status = "degraded"
    
    return {
        "status": health_status,
        "daily_slots": stats,
        "task_monitor": task_status
    }

@router.get("/monitoring/config", dependencies=[Depends(require_admin_role)])
async def get_monitoring_config():
    """Получение конфигурации мониторинга"""
    from app.core.config import settings
    
    return {
        "background_tasks": settings.background_task_config,
        "monitoring_interval": getattr(settings, 'TASK_MONITOR_INTERVAL', 600)
    }