import asyncio
from typing import Dict
import aioredis

class TimeoutManager:
    TIMEOUTS = {
        "embedding": 10.0,
        "chat_completion": 60.0,
        "reranking": 15.0,
        "evaluation": 120.0,
        "file_extraction": 30.0,
        "url_fetch": 15.0,
        "default": 30.0
    }
    
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
    
    async def with_timeout(self, coro: asyncio.Coroutine, task_type: str) -> Any:
        timeout = self.TIMEOUTS.get(task_type, self.TIMEOUTS["default"])
        
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            # Increment timeout counter
            await self.redis.incr(f"timeouts:{task_type}")
            await self.redis.expire(f"timeouts:{task_type}", 3600)  # 1hr TTL
            raise TimeoutError(f"Timeout after {timeout}s for {task_type}")