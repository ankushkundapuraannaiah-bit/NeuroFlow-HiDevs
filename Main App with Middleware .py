from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.middleware.security import SecurityMiddleware

app = FastAPI(title="NeuroFlow API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityMiddleware)

# Public endpoints (no auth required)
app.include_router(health_router, tags=["health"])  # /health, /metrics

# Protected routers
app.include_router(auth_router, tags=["auth"], dependencies=[Depends(get_current_user)])
app.include_router(pipelines_router, prefix="/pipelines", dependencies=[Depends(get_current_user)])
app.include_router(query_router, prefix="/query", dependencies=[Depends(require_scope("query"))])