from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import uuid
from backend.security.sanitizer import sanitize_text, validate_url
from backend.security.prompt_injection import detect_prompt_injection
from backend.security.secret_detector import detect_and_redact_secrets
import bleach
import json

class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        
        # Add security headers
        response = Response()
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Request-ID"] = request_id
        
        # Sanitize request body
        if request.method in ["POST", "PUT", "PATCH"] and request.headers.get("content-type", "").startswith("application/json"):
            body = await request.body()
            try:
                data = json.loads(body)
                sanitized_data = await self._sanitize_request_data(data)
                request._body = json.dumps(sanitized_data).encode()
            except:
                pass
        
        response = await call_next(request)
        return response
    
    async def _sanitize_request_data(self, data: dict) -> dict:
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if isinstance(v, str):
                    # Check for URLs
                    if k in ["url", "source_url"]:
                        if not validate_url(v):
                            raise HTTPException(400, f"Invalid URL: {v}")
                    
                    # Prompt injection detection for queries
                    if k in ["query", "question"]:
                        injection_meta = await detect_prompt_injection(v, is_query=True)
                        sanitized[k] = sanitize_text(v, "query")
                        if injection_meta["prompt_injection_detected"]:
                            sanitized["_security"] = injection_meta
                    else:
                        sanitized[k] = sanitize_text(v, k)
                elif isinstance(v, list):
                    sanitized[k] = [await self._sanitize_request_data(item) for item in v]
                else:
                    sanitized[k] = v
            return sanitized
        return data