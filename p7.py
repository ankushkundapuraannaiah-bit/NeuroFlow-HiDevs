from fastapi import APIRouter
import aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from backend.resilience.circuit_breaker import CircuitBreaker
from backend.resilience.backpressure import Backpressure

router = APIRouter()

@router.get("/health")
async def health_check(
    redis_client: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db)
):
    checks = {}
    
    # Database
    start = time.time()
    result = await db.execute(select(1))
    checks["postgres"] = {
        "status": "ok",
        "latency_ms": int((time.time() - start) * 1000)
    }
    
    # Redis
    start = time.time()
    await redis_client.ping()
    checks["redis"] = {
        "status": "ok", 
        "latency_ms": int((time.time() - start) * 1000)
    }
    
    # MLflow
    try:
        mlflow_client = MlflowClient()
        await mlflow_client.list_experiments(limit=1)
        checks["mlflow"] = {"status": "ok"}
    except:
        checks["mlflow"] = {"status": "error"}
    
    # Circuit breakers
    breakers = {}
    for name in ["openai", "anthropic", "cohere"]:
        cb = CircuitBreaker(redis_client, name)
        state = await cb.get_state()
        breakers[name] = {
            "state": state.value,
            "failure_count": await redis_client.get(f"circuit:{name}:failures") or 0
        }
    checks["circuit_breakers"] = breakers
    
    # Queue depth
    bp = Backpressure(redis_client)
    checks["queue_depth"] = await bp.get_ingest_queue_depth()
    
    # Worker count (from Redis key)
    checks["worker_count"] = await redis_client.get("worker:count") or 0
    
    # Overall status
    degraded = any(
        cb["state"] != "closed" for cb in breakers.values()
    ) or checks["queue_depth"] > 50
    
    status = "critical" if checks["postgres"]["status"] != "ok" else "degraded" if degraded else "ok"
    
    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }