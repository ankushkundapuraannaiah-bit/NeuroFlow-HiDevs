# API Contracts

**Version:** v1  
**Base URL:** `https://api.neuroflow.io/v1`  
**Auth:** All endpoints (except `/health` and `/metrics`) require `Authorization: Bearer <JWT>`.  
**Rate Limits:** Expressed as requests-per-minute (rpm) per authenticated user unless noted.

---

## Authentication

```
Authorization: Bearer <JWT>
```

JWTs are RS256-signed. Obtain tokens via `POST /auth/token` (not in scope here). Expired tokens return `401`. Tokens lacking the required scope return `403`.

---

## Common Error Schema

All 4xx/5xx responses use this envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": {}
  }
}
```

### Global Error Codes

| HTTP | Code | Meaning |
|------|------|---------|
| 400 | `VALIDATION_ERROR` | Request body fails schema validation |
| 401 | `UNAUTHORIZED` | Missing or invalid JWT |
| 403 | `FORBIDDEN` | Valid JWT but insufficient scope |
| 404 | `NOT_FOUND` | Resource does not exist |
| 409 | `CONFLICT` | Duplicate resource (e.g. same file hash) |
| 422 | `UNPROCESSABLE` | Semantically invalid input |
| 429 | `RATE_LIMITED` | Rate limit exceeded |
| 500 | `INTERNAL_ERROR` | Unexpected server error |
| 503 | `UNAVAILABLE` | Upstream dependency (LLM, vector store) unavailable |

---

## POST /ingest

Ingest a file or URL. The API queues the job and returns immediately.

**Auth:** Required  
**Rate Limit:** 60 rpm per user

### Request

`Content-Type: multipart/form-data` **or** `application/json`

**File upload (multipart):**

```
file: <binary>
pipeline_id: "pipe_abc123"          # optional — associate with named pipeline
tags: ["legal","2024"]              # optional — metadata tags
```

**URL ingestion (JSON):**

```json
{
  "url": "https://example.com/article",
  "pipeline_id": "pipe_abc123",
  "tags": ["web", "news"],
  "extract_links": false
}
```

### Response `202 Accepted`

```json
{
  "job_id": "job_7f3a9c",
  "document_id": null,
  "status": "QUEUED",
  "created_at": "2026-03-26T10:00:00Z",
  "estimated_completion_seconds": 30
}
```

### Error Codes

| HTTP | Code | Condition |
|------|------|-----------|
| 400 | `VALIDATION_ERROR` | Missing `file` and `url`, or both provided |
| 409 | `CONFLICT` | SHA-256 already ingested; returns existing `document_id` |
| 413 | `PAYLOAD_TOO_LARGE` | File > 50 MB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Mime type not in allowlist |

---

## POST /query

Execute a RAG query. Returns metadata immediately; generation is streamed via SSE.

**Auth:** Required  
**Rate Limit:** 120 rpm per user

### Request

```json
{
  "query": "What is the refund policy for international orders?",
  "pipeline_id": "pipe_abc123",
  "conversation_id": "conv_xyz789",
  "retrieval": {
    "top_n": 8,
    "filters": {
      "tags": ["policy"],
      "date_after": "2025-01-01"
    },
    "use_hyde": false
  },
  "generation": {
    "model_preference": "auto",
    "max_tokens": 1024,
    "temperature": 0.2,
    "stream": true
  }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `query` | string | Yes | 1–4096 chars |
| `pipeline_id` | string | No | Uses default pipeline if omitted |
| `conversation_id` | string | No | Enables multi-turn history |
| `retrieval.top_n` | int | No | Default 8, max 20 |
| `retrieval.filters` | object | No | Metadata filter predicates |
| `retrieval.use_hyde` | bool | No | Default false |
| `generation.model_preference` | string | No | `auto`, `gpt-4o`, `claude-3-5-sonnet`, `mistral` |
| `generation.max_tokens` | int | No | Default 1024, max 4096 |
| `generation.stream` | bool | No | Default true |

### Response `202 Accepted`

```json
{
  "query_id": "qry_4d8f12",
  "status": "PROCESSING",
  "stream_url": "/v1/query/qry_4d8f12/stream",
  "retrieved_chunks": [
    {
      "chunk_id": "chk_001",
      "document_id": "doc_abc",
      "score": 0.92,
      "text_preview": "International orders are eligible for...",
      "metadata": {
        "source": "policy-2025.pdf",
        "page": 4,
        "tags": ["policy"]
      }
    }
  ],
  "model_selected": "gpt-4o-mini",
  "created_at": "2026-03-26T10:05:00Z"
}
```

### Error Codes

| HTTP | Code | Condition |
|------|------|-----------|
| 400 | `VALIDATION_ERROR` | Query is empty or exceeds length |
| 404 | `NOT_FOUND` | `pipeline_id` does not exist |
| 503 | `UNAVAILABLE` | All LLM providers unavailable |

---

## GET /query/{query_id}/stream

Stream the generation response via Server-Sent Events.

**Auth:** Required  
**Rate Limit:** N/A (consumes a query credit from `/query`)

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `query_id` | string | Returned by `POST /query` |

### Response `200 OK`

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

**Event stream format:**

```
event: chunk
data: {"text": "International orders ", "index": 0}

event: chunk
data: {"text": "are eligible for full refunds ", "index": 1}

event: done
data: {"query_id": "qry_4d8f12", "total_tokens": 312, "latency_ms": 1842}

event: error
data: {"code": "GENERATION_FAILED", "message": "LLM timeout"}
```

### Error Codes

| HTTP | Code | Condition |
|------|------|-----------|
| 404 | `NOT_FOUND` | `query_id` not found |
| 410 | `GONE` | Stream expired (>5 min since query) |

---

## GET /evaluations

Paginated list of evaluation scores for generations.

**Auth:** Required  
**Rate Limit:** 60 rpm

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `pipeline_id` | string | — | Filter by pipeline |
| `model` | string | — | Filter by model name |
| `date_from` | ISO8601 | — | Start of date range |
| `date_to` | ISO8601 | — | End of date range |
| `min_faithfulness` | float | — | Lower bound on faithfulness score |
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Results per page, max 100 |

### Response `200 OK`

```json
{
  "data": [
    {
      "eval_id": "eval_001",
      "query_id": "qry_4d8f12",
      "generation_id": "gen_88ab",
      "model": "gpt-4o-mini",
      "pipeline_id": "pipe_abc123",
      "scores": {
        "faithfulness": 0.91,
        "answer_relevance": 0.87,
        "context_precision": 0.72,
        "context_recall": 0.68
      },
      "user_rating": 4,
      "evaluated_at": "2026-03-26T10:06:30Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 4821,
    "total_pages": 242
  }
}
```

---

## GET /evaluations/aggregate

Rolling aggregate metrics across all evaluations.

**Auth:** Required  
**Rate Limit:** 30 rpm

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `pipeline_id` | string | — | Filter by pipeline |
| `model` | string | — | Filter by model |
| `window` | string | `24h` | `1h`, `24h`, `7d`, `30d` |

### Response `200 OK`

```json
{
  "window": "24h",
  "pipeline_id": "pipe_abc123",
  "computed_at": "2026-03-26T10:00:00Z",
  "totals": {
    "evaluations": 312,
    "queries": 298
  },
  "averages": {
    "faithfulness": 0.86,
    "answer_relevance": 0.84,
    "context_precision": 0.70,
    "context_recall": 0.73
  },
  "percentiles": {
    "p50_faithfulness": 0.89,
    "p10_faithfulness": 0.62
  },
  "trend": {
    "faithfulness_delta_vs_prev_window": 0.02
  },
  "alerts": []
}
```

---

## POST /pipelines

Create a named pipeline configuration that bundles retrieval and generation settings.

**Auth:** Required  
**Rate Limit:** 20 rpm

### Request

```json
{
  "name": "Customer Support Pipeline",
  "description": "Handles support queries against product docs",
  "retrieval": {
    "dense_k": 50,
    "sparse_k": 50,
    "rerank_n": 100,
    "top_n": 8,
    "token_budget": 8192,
    "use_hyde": false,
    "default_filters": {
      "tags": ["support"]
    }
  },
  "generation": {
    "system_prompt": "You are a helpful customer support agent...",
    "model_preference": "auto",
    "max_tokens": 512,
    "temperature": 0.1
  },
  "evaluation": {
    "enabled": true,
    "auto_finetune_threshold": {
      "faithfulness": 0.8,
      "min_examples": 500
    }
  }
}
```

### Response `201 Created`

```json
{
  "pipeline_id": "pipe_abc123",
  "name": "Customer Support Pipeline",
  "created_at": "2026-03-26T09:00:00Z",
  "version": 1
}
```

### Error Codes

| HTTP | Code | Condition |
|------|------|-----------|
| 400 | `VALIDATION_ERROR` | Missing `name` or invalid config values |
| 409 | `CONFLICT` | Pipeline with this name already exists |

---

## GET /pipelines/{id}/runs

Execution history for a pipeline.

**Auth:** Required  
**Rate Limit:** 60 rpm

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `id` | string | Pipeline ID |

### Query Parameters

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | string | — | `QUEUED`, `RUNNING`, `DONE`, `FAILED` |
| `page` | int | 1 | — |
| `page_size` | int | 20 | Max 100 |

### Response `200 OK`

```json
{
  "pipeline_id": "pipe_abc123",
  "data": [
    {
      "run_id": "run_991",
      "triggered_by": "query",
      "query_id": "qry_4d8f12",
      "status": "DONE",
      "started_at": "2026-03-26T10:05:00Z",
      "finished_at": "2026-03-26T10:05:02Z",
      "latency_ms": 2140,
      "model_used": "gpt-4o-mini",
      "tokens_used": 1847
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1203,
    "total_pages": 61
  }
}
```

---

## POST /finetune/jobs

Submit a fine-tuning job using high-quality examples from the evaluation log.

**Auth:** Required (admin scope)  
**Rate Limit:** 5 rpm

### Request

```json
{
  "pipeline_id": "pipe_abc123",
  "base_model": "gpt-4o-mini-2024-07-18",
  "selection_criteria": {
    "min_faithfulness": 0.8,
    "min_user_rating": 4,
    "date_from": "2026-01-01",
    "max_examples": 5000
  },
  "hyperparameters": {
    "n_epochs": 3,
    "batch_size": "auto",
    "learning_rate_multiplier": "auto"
  },
  "description": "Customer support fine-tune Q1 2026"
}
```

### Response `202 Accepted`

```json
{
  "job_id": "ftjob_77cc",
  "status": "QUEUED",
  "base_model": "gpt-4o-mini-2024-07-18",
  "training_examples_selected": 2841,
  "validation_examples_selected": 316,
  "estimated_cost_usd": 12.40,
  "mlflow_run_id": "mlf_ab9c3",
  "created_at": "2026-03-26T09:30:00Z"
}
```

### Error Codes

| HTTP | Code | Condition |
|------|------|-----------|
| 400 | `VALIDATION_ERROR` | Invalid base model or criteria |
| 422 | `UNPROCESSABLE` | Fewer than 100 examples meet criteria |
| 409 | `CONFLICT` | Active job already running for this pipeline |

---

## GET /finetune/jobs/{id}

Status and metrics for a fine-tuning job.

**Auth:** Required  
**Rate Limit:** 60 rpm

### Path Parameters

| Param | Type | Description |
|-------|------|-------------|
| `id` | string | Fine-tuning job ID |

### Response `200 OK`

```json
{
  "job_id": "ftjob_77cc",
  "status": "RUNNING",
  "base_model": "gpt-4o-mini-2024-07-18",
  "fine_tuned_model": null,
  "training_examples": 2841,
  "hyperparameters": {
    "n_epochs": 3,
    "batch_size": 4
  },
  "metrics": {
    "train_loss": 0.42,
    "valid_loss": 0.51,
    "epochs_completed": 1,
    "estimated_finish_at": "2026-03-26T11:00:00Z"
  },
  "mlflow_run_url": "https://mlflow.neuroflow.io/runs/mlf_ab9c3",
  "created_at": "2026-03-26T09:30:00Z",
  "started_at": "2026-03-26T09:32:00Z",
  "finished_at": null,
  "promoted": false
}
```

**Status values:** `QUEUED` → `RUNNING` → `SUCCEEDED` → `PROMOTED` / `ARCHIVED`  
**On failure:** `FAILED` with `error_message` field populated.

---

## GET /health

Health check. No auth required. Used by load balancers and uptime monitors.

**Auth:** None  
**Rate Limit:** Unlimited

### Response `200 OK`

```json
{
  "status": "healthy",
  "version": "1.4.2",
  "checks": {
    "database": "ok",
    "vector_store": "ok",
    "redis": "ok",
    "llm_openai": "ok",
    "llm_anthropic": "degraded"
  },
  "uptime_seconds": 86400
}
```

**Degraded response `503`:**

```json
{
  "status": "degraded",
  "checks": {
    "database": "ok",
    "vector_store": "error"
  }
}
```

---

## GET /metrics

Prometheus-format metrics endpoint.

**Auth:** Internal network only (IP allowlist)  
**Rate Limit:** Unlimited

### Response `200 OK`

```
Content-Type: text/plain; version=0.0.4
```

```
# HELP neuroflow_ingest_jobs_total Total ingestion jobs by status
# TYPE neuroflow_ingest_jobs_total counter
neuroflow_ingest_jobs_total{status="success"} 15420
neuroflow_ingest_jobs_total{status="failed"} 83

# HELP neuroflow_query_latency_seconds Query end-to-end latency
# TYPE neuroflow_query_latency_seconds histogram
neuroflow_query_latency_seconds_bucket{le="0.5"} 1200
neuroflow_query_latency_seconds_bucket{le="2.0"} 4800
neuroflow_query_latency_seconds_bucket{le="+Inf"} 5102

# HELP neuroflow_eval_faithfulness_avg Rolling 1h average faithfulness
# TYPE neuroflow_eval_faithfulness_avg gauge
neuroflow_eval_faithfulness_avg 0.862
```

---

## Versioning Policy

The API is versioned via the URL path (`/v1/`). Breaking changes increment the major version. Deprecated endpoints return a `Deprecation` response header with the sunset date.
