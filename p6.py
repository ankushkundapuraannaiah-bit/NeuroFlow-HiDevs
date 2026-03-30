from backend.resilience.circuit_breaker import get_circuit_breaker
from backend.resilience.timeout_manager import TimeoutManager
from backend.resilience.rate_limiter import RateLimiter

class WrappedOpenAIClient:
    def __init__(self, redis_client, openai_client):
        self.redis = redis_client
        self.client = openai_client
        self.cb = get_circuit_breaker("openai", redis_client)
        self.tm = TimeoutManager(redis_client)
        self.rl = RateLimiter(redis_client)
    
    async def complete(self, messages, pipeline_id=None, rpm=None):
        async with self.rl.limit("openai", pipeline_id, rpm):
            async with self.cb(lambda: self._raw_complete(messages)):
                return await self.tm.with_timeout(
                    self._raw_complete(messages),
                    "chat_completion"
                )
    
    async def _raw_complete(self, messages):
        return await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.1
        )