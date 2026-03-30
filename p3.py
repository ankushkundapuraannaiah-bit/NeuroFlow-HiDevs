import aioredis

class Backpressure:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.ingest_queue = "queue:ingest"
        self.max_depth_critical = 100
        self.max_depth_warning = 50
    
    async def get_ingest_queue_depth(self) -> int:
        return await self.redis.llen(self.ingest_queue)
    
    async def check_ingestion_backpressure(self) -> Dict[str, Any]:
        """Check backpressure and return appropriate HTTP response info."""
        depth = await self.get_ingest_queue_depth()
        
        if depth > self.max_depth_critical:
            return {
                "status_code": 503,
                "error": "ingestion_queue_full",
                "queue_depth": depth,
                "retry_after": 30
            }
        elif depth > self.max_depth_warning:
            estimated_wait = (depth - self.max_depth_warning) * 0.5  # 30s per doc
            return {
                "status_code": 202,
                "warning": "high_queue_depth",
                "queue_depth": depth,
                "estimated_wait_minutes": round(estimated_wait / 60, 1)
            }
        else:
            return {"status_code": 200, "queue_depth": depth}