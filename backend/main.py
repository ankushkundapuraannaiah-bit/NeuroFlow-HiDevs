import os
import asyncpg
import redis.asyncio as redis
import httpx

from contextlib import asynccontextmanager
from fastapi import FastAPI
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# ------------------------------------------------------------------
# Environment variables
# ------------------------------------------------------------------

POSTGRES_USER = os.getenv("POSTGRES_USER", "neuroflow")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB", "neuroflow")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")

REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

MLFLOW_URL = os.getenv("MLFLOW_URL", "http://localhost:5000")

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:6379"

# ------------------------------------------------------------------
# OpenTelemetry Setup
# ------------------------------------------------------------------

resource = Resource.create({"service.name": "neuroflow-api"})

trace.set_tracer_provider(TracerProvider(resource=resource))
tracer_provider = trace.get_tracer_provider()

otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
span_processor = BatchSpanProcessor(otlp_exporter)

tracer_provider.add_span_processor(span_processor)

# ------------------------------------------------------------------
# Application state
# ------------------------------------------------------------------

class AppState:
    db_pool: asyncpg.Pool = None
    redis: redis.Redis = None


state = AppState()

# ------------------------------------------------------------------
# Lifespan Manager (startup / shutdown)
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):

    # Startup
    state.db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10
    )

    state.redis = redis.from_url(
        REDIS_URL,
        decode_responses=True
    )

    yield

    # Shutdown
    await state.db_pool.close()
    await state.redis.close()

# ------------------------------------------------------------------
# FastAPI App
# ------------------------------------------------------------------

app = FastAPI(
    title="Neuroflow API",
    version="1.0",
    lifespan=lifespan
)

FastAPIInstrumentor.instrument_app(app)

# ------------------------------------------------------------------
# Health checks
# ------------------------------------------------------------------

async def check_postgres():

    try:
        async with state.db_pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:
        return False


async def check_redis():

    try:
        await state.redis.ping()
        return True
    except Exception:
        return False


async def check_mlflow():

    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{MLFLOW_URL}/health")
        return r.status_code < 500
    except Exception:
        return False


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/health")
async def health():

    postgres_ok = await check_postgres()
    redis_ok = await check_redis()
    mlflow_ok = await check_mlflow()

    status = all([postgres_ok, redis_ok, mlflow_ok])

    return {
        "status": "ok" if status else "degraded",
        "checks": {
            "postgres": postgres_ok,
            "redis": redis_ok,
            "mlflow": mlflow_ok
        }
    }


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
