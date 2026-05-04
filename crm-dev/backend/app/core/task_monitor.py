# app/core/task_monitor.py
import asyncio
from typing import Dict, Any
from app.core.background_tasks import get_daily_slots_stats
from app.core.config import settings
import structlog

logger = structlog.get_logger(__name__)

class TaskMonitor:
    def __init__(self):
        self.task_status: Dict[str, Any] = {}
        self._shutdown_event = asyncio.Event()
        
    async def start_monitoring(self):
        """Запуск мониторинга фоновых задач"""
        logger.info("Task monitoring service started")
        
        # Первый запуск через 30 секунд после старта
        await asyncio.sleep(30)
        
        monitor_interval = getattr(settings, 'TASK_MONITOR_INTERVAL', 600)
        
        while not self._shutdown_event.is_set():
            try:
                # Собираем статистику
                daily_slots_stats = get_daily_slots_stats()
                
                self.task_status["daily_slots"] = {
                    **daily_slots_stats,
                    "status": self._evaluate_task_health(daily_slots_stats)
                }
                
                # Добавляем общую информацию
                self.task_status["monitoring"] = {
                    "last_check": asyncio.get_event_loop().time(),
                    "interval_seconds": monitor_interval
                }
                
                # Логируем статус
                if self.task_status["daily_slots"]["status"] != "healthy":
                    logger.warning(
                        "Background tasks health check",
                        tasks=self.task_status
                    )
                else:
                    logger.debug(
                        "Background tasks status",
                        tasks=self.task_status
                    )
                
                # Ждём следующий интервал
                await asyncio.wait_for(
                    self._shutdown_event.wait(), 
                    timeout=monitor_interval
                )
                
            except asyncio.TimeoutError:
                continue  # Нормально - время ожидания вышло
            except Exception as e:
                logger.error(
                    "Task monitoring error", 
                    error=str(e),
                    error_type=type(e).__name__
                )
                await asyncio.sleep(60)  # Ждём минуту при ошибках

        logger.info("Task monitoring service stopped")
    
    def _evaluate_task_health(self, stats: Dict[str, Any]) -> str:
        """Оценка здоровья фоновых задач"""
        try:
            # Проверяем последнее выполнение
            last_execution = stats.get("last_execution")
            if not last_execution:
                return "unknown"
            
            from datetime import datetime, timedelta
            last_time = datetime.fromisoformat(last_execution.replace('Z', '+00:00'))
            
            # Если последнее выполнение было более 24 часов назад
            if datetime.utcnow() - last_time > timedelta(hours=24):
                return "unhealthy"
            
            # Если много ошибок в последних выполнениях
            failure_count = stats.get("failure_count", 0)
            total_processed = stats.get("total_processed", 0)
            
            if total_processed > 0 and failure_count / total_processed > 0.5:
                return "degraded"
                
            return "healthy"
            
        except Exception as e:
            logger.error("Health evaluation failed", error=str(e))
            return "unknown"
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self._shutdown_event.set()
    
    def get_status(self) -> Dict[str, Any]:
        """Получение текущего статуса"""
        return self.task_status

# Глобальный экземпляр монитора
task_monitor = TaskMonitor()