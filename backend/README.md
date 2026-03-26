Neuroflow AI Backend Infrastructure

A production-ready AI backend foundation built with modern tools for developing RAG systems, AI pipelines, and model evaluation workflows.

This stack provides:

Vector database with pgvector
Fast API service using FastAPI
Background processing workers
Redis caching and queues
MLflow experiment tracking
Jaeger distributed tracing
Prometheus metrics
Structured pipeline and evaluation storage

Designed for AI research, LLM pipelines, and retrieval-augmented generation systems.

Architecture

The system runs using Docker Compose and includes the following services:

Service	Purpose
PostgreSQL + pgvector	Stores documents, embeddings, pipelines
Redis	Cache and background task queue
MLflow	Machine learning experiment tracking
FastAPI API	Main backend API
Worker	Background tasks (chunking, embeddings, pipelines)
Jaeger	Distributed tracing and performance debugging

Architecture overview:

                ┌─────────────┐
                │   FastAPI   │
                │    API      │
                └──────┬──────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   PostgreSQL       Redis         MLflow
   + pgvector      Cache/Queue    Experiments
        │
        │
     Worker
  (background tasks)

Tracing: Jaeger
Metrics: Prometheus
Features
Vector Search

Uses pgvector for semantic search with HNSW indexing.

Document Pipeline

Documents are stored and split into chunks for retrieval.

AI Pipeline Tracking

Tracks queries, responses, token usage, and latency.

Evaluation Framework

Stores metrics like:

Faithfulness
Answer relevance
Context precision
Context recall
Fine-Tuning Support

Stores conversation training pairs and fine-tuning jobs.

Observability

Built-in monitoring tools:

Jaeger for tracing
Prometheus metrics
health monitoring endpoints
Project Structure
project-root
│
├── backend
│   ├── main.py
│   ├── config.py
│   ├── worker.py
│   └── db
│       ├── pool.py
│       ├── health.py
│       └── migrations.py
│
├── infra
│   ├── docker-compose.yml
│   └── init
│       └── 001_schema.sql
│
├── .env
└── README.md
Database Schema

The system includes structured tables for AI workflows.

documents

Stores uploaded data sources.

chunks

Stores document chunks with vector embeddings.

pipelines

Defines AI pipelines and configuration.

pipeline_runs

Logs every AI query and generated response.

evaluations

Stores automatic evaluation metrics.

training_pairs

Conversation examples for fine-tuning.

finetune_jobs

Tracks model training jobs.

Prerequisites

Install:

Docker
Docker Compose
Python 3.10+
Git
Setup Instructions
1 Clone Repository
git clone https://github.com/yourusername/neuroflow.git
cd neuroflow
2 Create Environment Variables

Create .env

Example:

POSTGRES_USER=neuroflow
POSTGRES_PASSWORD=securepassword
POSTGRES_DB=neuroflow

REDIS_PASSWORD=securepassword

OPENAI_API_KEY=your_api_key
3 Start Infrastructure
cd infra
docker compose up -d

This starts:

Postgres
Redis
MLflow
Jaeger
4 Start Backend API
cd backend

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload

API runs at:

http://localhost:8000
Service URLs
Service	URL
API	http://localhost:8000

API Docs	http://localhost:8000/docs

MLflow	http://localhost:5000

Jaeger	http://localhost:16686
Health Check Endpoint
GET /health

Example response:

{
  "status": "ok",
  "checks": {
    "postgres": true,
    "redis": true,
    "mlflow": true
  }
}
Metrics Endpoint

Prometheus compatible metrics:

GET /metrics
Database Verification

Enter Postgres container:

docker exec -it postgres psql -U neuroflow -d neuroflow

Verify chunk table:

\d+ chunks

You should see:

vector(1536) column
HNSW vector index
full text search index
Observability
Jaeger Tracing

View distributed traces:

http://localhost:16686
MLflow

Track experiments and model runs:

http://localhost:5000
Development Workflow

Start infrastructure:

docker compose up -d

Run backend:

uvicorn main:app --reload

Run worker:

python -m worker
Tech Stack

Backend:

FastAPI
asyncpg
Redis
Pydantic Settings

Infrastructure:

Docker
PostgreSQL
pgvector

ML:

MLflow

Observability:

OpenTelemetry
Jaeger
Prometheus
Future Improvements

Planned additions:

automatic document ingestion
embedding generation pipelines
LLM orchestration
evaluation dashboards
automated fine-tuning pipelines
agent workflow support
License

MIT License
