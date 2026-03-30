from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from backend.resilience.rate_limiter import EndpointRateLimiter
import aioredis

class ResilienceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_client):
        super().__init__(app)
        self.rate_limiter = EndpointRateLimiter(redis_client)
        self.redis = redis_client
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        
        # Endpoint rate limits
        limits = {
            "/ingest": (3600, 10),  # 10/hour
            "/query": (60, 60),     # 60/minute
        }
        
        endpoint = request.url.path
        if endpoint in limits:
            window, max_req = limits[endpoint]
            retry_after = await self.rate_limiter.check_endpoint_limit(
                client_ip, endpoint, window, max_req
            )
            if retry_after:
                raise HTTPException(
                    429,
                    headers={"Retry-After": str(retry_after)},
                    detail=f"Rate limit exceeded. Retry after {retry_after}s"
                )
        
        response = await call_next(request)
        return response