import asyncio
import time
import uuid
from typing import Callable, Any, AsyncGenerator
from contextlib import asynccontextmanager
import aioredis
from dataclasses import dataclass
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitOpenError(Exception):
    circuit_name: str
    state: CircuitState
    opened_at: float

class CircuitBreaker:
    def __init__(
        self,
        redis_client,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3
    ):
        self.redis = redis_client
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.key_state = f"circuit:{name}:state"
        self.key_failures = f"circuit:{name}:failures"
        self.key_opened_at = f"circuit:{name}:opened_at"
        self.key_half_open_count = f"circuit:{name}:half_open_count"
    
    async def get_state(self) -> CircuitState:
        state = await self.redis.get(self.key_state)
        if state == b"open":
            opened_at = await self.redis.get(self.key_opened_at)
            if opened_at and time.time() - float(opened_at) > self.recovery_timeout:
                await self._transition_to_half_open()
                return CircuitState.HALF_OPEN
            return CircuitState.OPEN
        elif state == b"half_open":
            return CircuitState.HALF_OPEN
        return CircuitState.CLOSED
    
    async def _transition_to_open(self):
        await self.redis.set(self.key_state, "open")
        await self.redis.set(self.key_opened_at, time.time())
    
    async def _transition_to_half_open(self):
        await self.redis.set(self.key_state, "half_open")
        await self.redis.set(self.key_half_open_count, 0)
    
    async def _transition_to_closed(self):
        await self.redis.set(self.key_state, "closed")
        await self.redis.delete(self.key_failures, self.key_opened_at, self.key_half_open_count)
    
    async def _record_failure(self):
        failures = await self.redis.incr(self.key_failures)
        if failures >= self.failure_threshold:
            await self._transition_to_open()
    
    async def _record_success(self):
        state = await self.get_state()
        if state == CircuitState.HALF_OPEN:
            count = await self.redis.incr(self.key_half_open_count)
            if count >= self.half_open_max_calls:
                await self._transition_to_closed()
        else:
            await self.redis.delete(self.key_failures)
    
    @asynccontextmanager
    async def __call__(self, coro: Callable) -> AsyncGenerator[Any, None]:
        state = await self.get_state()
        
        if state == CircuitState.OPEN:
            opened_at = await self.redis.get(self.key_opened_at)
            raise CircuitOpenError(
                circuit_name=self.name,
                state=state,
                opened_at=float(opened_at) if opened_at else 0
            )
        
        try:
            result = await coro()
            await self._record_success()
            yield result
        except Exception as e:
            await self._record_failure()
            raise

# Global breakers
circuit_breakers = {}

async def get_circuit_breaker(name: str, redis_client) -> CircuitBreaker:
    if name not in circuit_breakers:
        circuit_breakers[name] = CircuitBreaker(redis_client, name)
    return circuit_breakers[name]