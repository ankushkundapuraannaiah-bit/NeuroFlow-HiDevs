# NeuroFlow Architecture

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2026-03-26

---

## Overview

NeuroFlow is structured as five loosely coupled subsystems, each owning a distinct concern. They communicate via an internal event bus (Redis Streams) and a shared PostgreSQL database. All subsystems expose metrics to a Prometheus scrape endpoint and log structured JSON to the central log aggregator.

```
┌──────────────────────────────────────────────────────────────┐
│                        NeuroFlow Platform                     │
│                                                               │
│  ┌──────────┐  ┌───────────┐  ┌────────────┐                │
│  │ Ingestion│  │ Retrieval │  │ Generation │                 │
│  └────┬─────┘  └─────┬─────┘  └─────┬──────┘                │
│       │              │              │                         │
│  ┌────▼──────────────▼──────────────▼──────┐                │
│  │           Shared Data Layer              │                │
│  │   pgvector  │  PostgreSQL  │  Redis       │                │
│  └────┬──────────────────────────────┬─────┘                │
│       │                              │                        │
│  ┌────▼──────┐               ┌───────▼──────┐               │
│  │ Evaluation│               │ Fine-Tuning  │               │
│  └───────────┘               └──────────────┘               │
└──────────────────────────────────────────────────────────────┘
```

---

## 1. Ingestion Subsystem

### Purpose

Accept raw files and URLs in any supported modality, extract and normalize content, chunk it into retrieval-optimal segments, embed each chunk, and write the resulting vectors plus metadata to the vector store so they are immediately queryable.

### Supported Modalities

| Input Type | Extraction Method |
|-----------|------------------|
| PDF | PyMuPDF (text) + Tesseract OCR (scanned pages) |
| DOCX | python-docx → plain text |
| Images (PNG/JPG) | GPT-4o Vision captioning + OCR |
| CSV / JSON | Structured → row-level serialization |
| Web URL | Playwright headless browser → Readability parse |

### Data Flow

```
File Upload / URL
       │
       ▼
┌─────────────────┐
│  Ingest API     │  POST /ingest
│  (FastAPI)      │  Validates mime type, queues job
└────────┬────────┘
         │ publishes job_id → Redis Stream: ingest.jobs
         ▼
┌─────────────────┐
│  Ingest Worker  │  Pulls from Redis Stream
│  (Celery)       │
└────────┬────────┘
         │
    ┌────▼──────────────────────────┐
    │        Extraction Router      │
    │  PDF? → PyMuPDF + OCR         │
    │  DOCX? → python-docx          │
    │  Image? → Vision API          │
    │  CSV? → row serializer        │
    │  URL? → Playwright parser     │
    └────────────┬──────────────────┘
                 │ raw_text + metadata
                 ▼
    ┌────────────────────────────────┐
    │         Chunker                │
    │  Strategy: semantic (default)  │
    │  Fallback: sentence-boundary   │
    │  Emergency: fixed-size 512t    │
    │  Output: List[Chunk]           │
    └────────────┬───────────────────┘
                 │ chunks
                 ▼
    ┌────────────────────────────────┐
    │         Embedder               │
    │  Model: text-embedding-3-large │
    │  Batch size: 100 chunks        │
    │  Fallback: local BGE-M3        │
    └────────────┬───────────────────┘
                 │ (chunk_text, embedding[1536], metadata)
                 ▼
    ┌────────────────────────────────┐
    │       Vector Store Writer      │
    │  Table: document_chunks        │
    │  pgvector HNSW index           │
    │  Also writes: BM25 tsvector    │
    └────────────┬───────────────────┘
                 │
                 ▼
    ┌────────────────────────────────┐
    │   Status Update (Postgres)     │
    │  ingest_jobs.status = DONE     │
    │  Publishes: ingest.completed   │
    └────────────────────────────────┘
```

### Key Design Decisions

- **Async ingestion**: All work happens in background workers. The API returns `job_id` immediately with HTTP 202.
- **Idempotency**: File SHA-256 hash is checked before re-processing. Duplicate uploads return the existing `document_id`.
- **Metadata preservation**: Page number, section heading, file name, and source URL are stored alongside every chunk for downstream filtering.
- **Error handling**: Failed chunks are retried up to 3 times with exponential backoff. Permanently failed jobs are written to a dead-letter table.

---

## 2. Retrieval Subsystem

### Purpose

Given a user query, retrieve the most relevant context chunks from the vector store using a multi-signal, multi-stage pipeline that combines semantic similarity, keyword matching, and metadata filtering, then fuses and reranks results before returning a ranked context window to the generation subsystem.

### Retrieval Pipeline

```
User Query (string)
       │
       ▼
┌─────────────────┐
│  Query Analysis │
│  - intent class │
│  - metadata     │
│    filter parse │
│  - HyDE expand  │  (optional: generate hypothetical doc)
└────────┬────────┘
         │
    ┌────┴─────────────────────────────────┐
    │           Parallel Search            │
    │                                      │
    │  ┌─────────────┐  ┌───────────────┐ │
    │  │ Dense Search│  │ Sparse Search │ │
    │  │  pgvector   │  │ BM25 tsvector │ │
    │  │  cosine sim │  │ ts_rank_cd    │ │
    │  │  top-k=50   │  │ top-k=50      │ │
    │  └──────┬──────┘  └───────┬───────┘ │
    │         │                 │         │
    │  ┌──────▼─────────────────▼───────┐ │
    │  │    Metadata Filter Gate        │ │
    │  │  (doc_type, date_range, tags)  │ │
    │  └──────────────┬─────────────────┘ │
    └─────────────────┼───────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │  Reciprocal Rank Fusion │
         │  RRF(d) = Σ 1/(k + r)  │
         │  k=60 (standard)       │
         │  Produces unified list │
         └────────────┬───────────┘
                      │ top-100 candidates
                      ▼
         ┌────────────────────────┐
         │   Cross-Encoder        │
         │   Reranker             │
         │  Model: ms-marco-      │
         │  MiniLM-L-6-v2         │
         │  Scores all 100 pairs  │
         └────────────┬───────────┘
                      │ sorted by rerank score
                      ▼
         ┌────────────────────────┐
         │   Context Window       │
         │   Assembler            │
         │  - Top N chunks        │
         │  - Token budget: 8192  │
         │  - Dedup by content    │
         │  - Add citations       │
         └────────────────────────┘
                      │
                      ▼
              [Ranked Context Window]
              → passed to Generation
```

### Retrieval Parameters (Configurable per Pipeline)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dense_k` | 50 | Candidates from vector search |
| `sparse_k` | 50 | Candidates from BM25 |
| `rerank_n` | 100 | Docs fed to cross-encoder |
| `top_n` | 8 | Final chunks in context window |
| `token_budget` | 8192 | Max tokens in context |
| `rrf_k` | 60 | RRF smoothing constant |
| `use_hyde` | false | Enable hypothetical document expansion |

---

## 3. Generation Subsystem

### Purpose

Assemble the ranked context window into a structured prompt, route the request to the most appropriate LLM based on cost tier, capability level, or domain specialization, stream the response token by token via SSE, and log the complete input/output pair for downstream evaluation.

### Generation Pipeline

```
[Ranked Context Window] + [User Query] + [Conversation History]
       │
       ▼
┌─────────────────────────────────┐
│        Prompt Assembler         │
│  - System prompt template       │
│  - Context injection (citations)│
│  - Query + history              │
│  - Output format instructions   │
└────────────────┬────────────────┘
                 │ assembled_prompt
                 ▼
┌─────────────────────────────────┐
│          LLM Router             │
│                                 │
│  Rules (evaluated in order):    │
│  1. Fine-tuned model available  │
│     AND query matches domain?   │
│     → Route to fine-tuned model │
│  2. query_complexity == HIGH    │
│     → GPT-4o / Claude 3.5 Sonnet│
│  3. query_complexity == MEDIUM  │
│     → GPT-4o-mini / Haiku       │
│  4. default                     │
│     → Cost-optimized (Mistral)  │
└────────────────┬────────────────┘
                 │ selected_model + prompt
                 ▼
┌─────────────────────────────────┐
│        LLM Client               │
│  - OpenAI / Anthropic / Mistral │
│  - Streaming enabled            │
│  - Timeout: 30s                 │
│  - Retry on 429/500: 3x         │
└────────────────┬────────────────┘
                 │ token stream
                 ▼
┌─────────────────────────────────┐
│      SSE Stream Handler         │
│  GET /query/{id}/stream         │
│  Content-Type: text/event-stream│
│  Buffers tokens, flushes ≤50ms  │
└────────────────┬────────────────┘
                 │ on stream complete
                 ▼
┌─────────────────────────────────┐
│        Generation Logger        │
│  Writes to: generation_logs     │
│  Fields:                        │
│    query_id, user_id,           │
│    model_used, prompt_tokens,   │
│    completion_tokens, latency,  │
│    full_prompt, full_response,  │
│    retrieved_chunk_ids          │
│  Publishes: eval.pending event  │
└─────────────────────────────────┘
```

### LLM Routing Matrix

| Condition | Model | Estimated Cost/1K tokens |
|-----------|-------|--------------------------|
| Fine-tuned match | Custom ft-model | $0.003 |
| High complexity | GPT-4o / Claude Sonnet | $0.015 |
| Medium complexity | GPT-4o-mini | $0.00015 |
| Default / bulk | Mistral 7B (self-hosted) | $0.0001 |

---

## 4. Evaluation Subsystem

### Purpose

Asynchronously score every generation on four RAG quality dimensions, persist scores to Postgres, and compute rolling aggregate metrics that surface quality trends and regressions on a per-pipeline and per-model basis.

### Evaluation Pipeline

```
eval.pending event (from Generation Logger)
       │
       ▼
┌─────────────────────────────────┐
│     Evaluation Worker           │
│  (Celery, async, low priority)  │
│  Fetches: generation_log entry  │
│  + retrieved chunks             │
└────────────────┬────────────────┘
                 │
    ┌────────────┴──────────────────────────┐
    │         Four Parallel Scorers          │
    │                                        │
    │  ┌──────────────┐  ┌───────────────┐  │
    │  │ Faithfulness │  │Ans. Relevance │  │
    │  │              │  │               │  │
    │  │ Q: Are claims│  │ Q: Does answer│  │
    │  │ grounded in  │  │ address the   │  │
    │  │ context?     │  │ question?     │  │
    │  │              │  │               │  │
    │  │ Method:      │  │ Method:       │  │
    │  │ LLM-as-judge │  │ LLM-as-judge  │  │
    │  │ + NLI model  │  │ + cosine sim  │  │
    │  │ Score: 0-1   │  │ Score: 0-1    │  │
    │  └──────┬───────┘  └───────┬───────┘  │
    │         │                  │           │
    │  ┌──────▼───────┐  ┌───────▼───────┐  │
    │  │ Ctx Precision│  │ Ctx Recall    │  │
    │  │              │  │               │  │
    │  │ Q: Were all  │  │ Q: Were all   │  │
    │  │ retrieved    │  │ relevant docs │  │
    │  │ chunks used? │  │ retrieved?    │  │
    │  │              │  │               │  │
    │  │ Method:      │  │ Method:       │  │
    │  │ Chunk usage  │  │ Attribution   │  │
    │  │ attribution  │  │ coverage      │  │
    │  │ Score: 0-1   │  │ Score: 0-1    │  │
    │  └──────┬───────┘  └───────┬───────┘  │
    └─────────┼──────────────────┼──────────┘
              │                  │
              └────────┬─────────┘
                       │ all four scores
                       ▼
         ┌─────────────────────────┐
         │    Score Persistence    │
         │  Table: eval_scores     │
         │  + generation_id FK     │
         │  + model_used           │
         │  + pipeline_id          │
         │  + timestamp            │
         └────────────┬────────────┘
                      │
                      ▼
         ┌─────────────────────────┐
         │   Rolling Aggregates    │
         │  Materialized view,     │
         │  refreshed every 5min   │
         │  Dimensions:            │
         │  - per pipeline         │
         │  - per model            │
         │  - per time window      │
         │    (1h, 24h, 7d, 30d)  │
         │  Alerts if faithfulness │
         │  drops below 0.75       │
         └─────────────────────────┘
```

### Metric Definitions

| Metric | Formula | Threshold |
|--------|---------|-----------|
| **Faithfulness** | Claims verified in context / total claims | ≥ 0.80 |
| **Answer Relevance** | Cosine(answer_embedding, question_embedding) | ≥ 0.75 |
| **Context Precision** | Used chunks / retrieved chunks | ≥ 0.60 |
| **Context Recall** | Retrieved relevant / total relevant | ≥ 0.70 |

---

## 5. Fine-Tuning Subsystem

### Purpose

Continuously mine the evaluation log for high-quality prompt/completion examples, format them as JSONL training data, submit fine-tuning jobs to the model provider, track all experiments in MLflow, and route future queries to the fine-tuned model when it demonstrably outperforms the base model.

### Fine-Tuning Pipeline

```
Scheduled Trigger (daily, or manual via POST /finetune/jobs)
       │
       ▼
┌─────────────────────────────────────┐
│         Example Extractor           │
│                                     │
│  SQL query:                         │
│  SELECT g.full_prompt,              │
│         g.full_response,            │
│         g.retrieved_chunk_ids       │
│  FROM generation_logs g             │
│  JOIN eval_scores e ON g.id = e.gid │
│  WHERE e.faithfulness > 0.8         │
│    AND e.user_rating >= 4           │
│    AND g.used_in_training = false   │
│  LIMIT 10000                        │
└────────────────┬────────────────────┘
                 │ raw training candidates
                 ▼
┌─────────────────────────────────────┐
│         JSONL Formatter             │
│                                     │
│  Format: OpenAI chat fine-tune      │
│  {"messages": [                     │
│    {"role": "system", "content":…}, │
│    {"role": "user",   "content":…}, │
│    {"role": "assistant","content":…}│
│  ]}                                 │
│                                     │
│  Dedup by fuzzy prompt similarity   │
│  Min examples: 500                  │
│  Max examples: 10000                │
│  Train/val split: 90/10             │
└────────────────┬────────────────────┘
                 │ train.jsonl, val.jsonl
                 ▼
┌─────────────────────────────────────┐
│       Fine-Tune Job Submitter       │
│                                     │
│  Provider: OpenAI Fine-Tuning API   │
│  Base model: gpt-4o-mini-2024-07-18 │
│  Hyperparams: n_epochs=3 (default)  │
│  Polls status every 5 min           │
└────────────────┬────────────────────┘
                 │ job_id, model_id (on completion)
                 ▼
┌─────────────────────────────────────┐
│        MLflow Experiment Tracker    │
│                                     │
│  Logs:                              │
│  - Training data size               │
│  - Base model name                  │
│  - Hyperparameters                  │
│  - val_loss (from provider)         │
│  - Post-eval scores (faithfulness,  │
│    answer_relevance)                │
│  - Training cost ($)                │
│  - Training duration                │
└────────────────┬────────────────────┘
                 │ on job complete
                 ▼
┌─────────────────────────────────────┐
│        Model Promotion Gate         │
│                                     │
│  Runs A/B eval on 200 held-out      │
│  queries:                           │
│                                     │
│  IF fine-tuned.faithfulness >       │
│     base.faithfulness + 0.05        │
│  AND fine-tuned.answer_relevance >= │
│     base.answer_relevance           │
│  THEN:                              │
│    → Register model in model registry│
│    → Update LLM Router rules        │
│    → Route matching domain queries  │
│      to fine-tuned model            │
│  ELSE:                              │
│    → Archive model, keep base       │
└─────────────────────────────────────┘
```

### Model Routing After Promotion

Fine-tuned models are assigned a **domain tag** derived from the topic distribution of their training data. The LLM Router checks for domain match (cosine similarity > 0.7 between query embedding and domain centroid) before routing to the fine-tuned model.

---

## Cross-Cutting Concerns

### Authentication

All API endpoints require a Bearer token (JWT, RS256). Service-to-service calls use mTLS.

### Observability

- **Metrics**: Prometheus + Grafana (latency p50/p95/p99, throughput, error rate per subsystem)
- **Tracing**: OpenTelemetry → Jaeger (trace spans from ingestion through generation)
- **Logging**: Structured JSON → Loki / Elasticsearch

### Data Residency

All embeddings and generation logs are stored in the primary Postgres instance (region-configurable). No data is sent to external services except the LLM providers defined in the router.
