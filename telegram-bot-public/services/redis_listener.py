"""
Сервис для прослушивания событий из Redis
"""
import asyncio
import json
import structlog
from typing import Callable, Optional
import redis.asyncio as redis

logger = structlog.get_logger(__name__)


class RedisListener:
    """Слушатель событий из Redis Pub/Sub"""
    
    def __init__(self, redis_url: str, channel: str, callback: Callable):
        self.redis_url = redis_url
        self.channel = channel
        self.callback = callback
        self.redis: Optional[redis.Redis] = None
        self.pubsub = None
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._reconnect_delay = 1  # seconds, with exponential backoff
    
    async def start(self):
        """Запуск слушателя"""
        try:
            self.redis = redis.from_url(self.redis_url, decode_responses=True)
            self.pubsub = self.redis.pubsub()
            await self.pubsub.subscribe(self.channel)
            
            self.running = True
            self._reconnect_delay = 1
            logger.info("Redis listener started", channel=self.channel)
            
            # Запускаем задачу прослушивания (сохраняем ссылку)
            self._task = asyncio.create_task(self._listen())
            
        except Exception as e:
            logger.error("Failed to start Redis listener", error=str(e))
            raise
    
    async def _reconnect(self):
        """Переподключение к Redis с экспоненциальным backoff"""
        while self.running:
            try:
                logger.info("Attempting Redis reconnection...", delay=self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                
                # Закрываем старые соединения
                try:
                    if self.pubsub:
                        await self.pubsub.close()
                    if self.redis:
                        await self.redis.close()
                except Exception:
                    pass
                
                self.redis = redis.from_url(self.redis_url, decode_responses=True)
                self.pubsub = self.redis.pubsub()
                await self.pubsub.subscribe(self.channel)
                self._reconnect_delay = 1  # Reset on success
                logger.info("Redis reconnected successfully", channel=self.channel)
                return
            except Exception as e:
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)
                logger.error("Redis reconnection failed", error=str(e), next_delay=self._reconnect_delay)
    
    async def _listen(self):
        """Прослушивание сообщений из Redis"""
        while self.running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True, 
                    timeout=1.0
                )
                
                if message and message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        logger.debug("Received Redis message", channel=self.channel, type=data.get('type'))
                        await self.callback(data)
                    except json.JSONDecodeError as e:
                        logger.warning("Failed to parse Redis message", error=str(e), data=message['data'])
                    except Exception as e:
                        logger.error("Error processing Redis message", error=str(e))
                
            except asyncio.CancelledError:
                break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Error in Redis listener, attempting reconnection", error=str(e))
                await self._reconnect()
    
    async def stop(self):
        """Остановка слушателя"""
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.pubsub:
            await self.pubsub.unsubscribe(self.channel)
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()
        logger.info("Redis listener stopped")