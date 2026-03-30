import asyncio
import time
import aioredis
from typing import Optional
from contextlib import asynccontextmanager

class TokenBucket:
    def __init__(self, redis_client, key: str, capacity: int, refill_rate: float):
        self.redis = redis_client
        self.key = key
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
    
    async def _refill(self):
        """Background refill task."""
        now = time.time()
        last_refill = await self.redis.get(f"{self.key}:last_refill")
        last_refill = float(last_refill) if last_refill else now
        
        tokens_to_add = (now - last_refill) * self.refill_rate
        current = await self.redis.get(self.key)
        current = float(current) if current else 0
        
        new_level = min(self.capacity, current + tokens_to_add)
        await self.redis.set(self.key, new_level)
        await self.redis.set(f"{self.key}:last_refill", now)
    
    async def consume(self, tokens: int = 1, max_wait: float = 10.0) -> bool:
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            await self._refill()
            
            current = await self.redis.get(self.key)
            current = float(current) if current else 0
            
            if current >= tokens:
                await self.redis.decrby(self.key, tokens)
                return True
            
            await asyncio.sleep(0.1)
        
        return False

class RateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.global_limits = {
            "openai": TokenBucket(redis_client, "rpb:global:openai", 3000, 50.0),
            "anthropic": TokenBucket(redis_client, "rpb:global:anthropic", 1000, 16.67),
        }
    
    async def check_global_limit(self, provider: str) -> bool:
        bucket = self.global_limits.get(provider)
        if not bucket:
            return True
        return await bucket.consume()
    
    async def check_pipeline_limit(self, pipeline_id: str, rpm: int) -> bool:
        """Per-pipeline limit: rpm -> tokens/sec."""
        if rpm <= 0:
            return True
        
        refill_rate = rpm / 60.0
        bucket = TokenBucket(
            self.redis,
            f"rpb:pipeline:{pipeline_id}",
            rpm,  # 1-minute capacity
            refill_rate
        )
        return await bucket.consume()
    
    @asynccontextmanager
    async def limit(self, provider: str, pipeline_id: Optional[str] = None, rpm: Optional[int] = None):
        if not await self.check_global_limit(provider):
            raise Exception(f"Global rate limit exceeded for {provider}")
        
        if pipeline_id and rpm:
            if not await self.check_pipeline_limit(pipeline_id, rpm):
                raise Exception(f"Pipeline rate limit exceeded: {pipeline_id}")
        
        yield

# API endpoint rate limiting (sliding window)
class EndpointRateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def check_endpoint_limit(
        self,
        client_ip: str,
        endpoint: str,
        window_seconds: int,
        max_requests: int
    ) -> Optional[int]:
        key = f"rate_limit:{endpoint}:{client_ip}"
        now = int(time.time())
        window_start = now - window_seconds
        
        # Remove expired requests
        await self.redis.zremrangebyscore(key, 0, window_start)
        
        # Count current requests
        count = await self.redis.zcard(key)
        if count >= max_requests:
            # Return seconds until window resets
            retry_after = window_seconds - (now % window_seconds)
            return retry_after
        
        # Add current request
        await self.redis.zadd(key, {str(now): now})
        await self.redis.expire(key, window_seconds)
        return None