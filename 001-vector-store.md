# ADR 001 — Vector Store Selection

**Status:** Accepted  
**Date:** 2026-03-26  
**Deciders:** Platform Team

---

## Context

NeuroFlow needs a vector store to hold chunk embeddings (1536 dimensions, text-embedding-3-large) and serve approximate nearest-neighbor (ANN) queries at sub-200ms p95. The store must also support hybrid search — combining dense vector similarity with BM25 keyword ranking — and rich metadata filtering (date ranges, tags, document type). We evaluated four candidates:

**Pinecone** is a fully managed cloud-native vector database with strong ANN performance, a generous free tier, and a simple SDK. However, it is a separate service with no SQL semantics, requires syncing metadata into a shadow relational store, and introduces a hard vendor dependency. Its serverless pricing scales linearly with index size and query volume, becoming expensive above ~50M vectors.

**Weaviate** is an open-source vector database with a GraphQL interface and built-in BM25/hybrid search. It supports multi-tenancy and has a managed cloud offering. Operational complexity is high: it runs as a separate stateful service with its own persistence layer (Raft for clustering), and its schema system is opinionated, requiring module configuration for each embedding model.

**Qdrant** is a Rust-based open-source vector database with excellent ANN performance, filterable payloads, and sparse vector support (SPLADE). It runs as a standalone service and has a clean REST/gRPC API. Like Weaviate, it adds infrastructure surface area and is not co-located with the relational data.

**pgvector** is a PostgreSQL extension that adds `VECTOR` columns with HNSW and IVFFlat index support. It runs inside the same PostgreSQL instance we already require for relational data (users, pipelines, eval scores).

---

## Decision

We will use **pgvector** as the vector store for NeuroFlow v1.

The core reasons are:

**Operational simplicity.** NeuroFlow already depends on PostgreSQL for all relational data. Adding pgvector means zero additional services to deploy, monitor, back up, or on-call. Every new service in the data layer multiplies operational burden, on-call scope, and failure modes.

**Hybrid search without ETL.** pgvector's `VECTOR` columns sit in the same table as `TSVECTOR` full-text search columns. A single query can execute both an ANN cosine search and a BM25 `ts_rank_cd` keyword search, then join the results in SQL for Reciprocal Rank Fusion — with no data synchronization pipeline.

**Rich metadata filtering.** PostgreSQL's `JSONB` operators, GIN indexes, and composable `WHERE` clauses give us arbitrary metadata filters at no extra cost. Pinecone and Qdrant both support filtering but require learning a separate filter DSL.

**Transactional consistency.** Chunk inserts, document metadata writes, and job status updates all happen in the same ACID transaction. There is no risk of a crash leaving the relational record and the vector index out of sync.

**Scale adequacy.** At the projected v1 scale (≤10M chunks, ~16 GB embedding data), pgvector HNSW delivers ANN recall above 0.95 at p95 latency under 50ms on a `c5.2xlarge` equivalent. Pinecone's latency advantage only materializes above 100M vectors.

---

## Consequences

**Positive:**

- One Postgres instance to operate, monitor, back up, and scale.
- Hybrid search is a single SQL query; no cross-service result fusion required.
- Transactional writes keep relational metadata and vectors consistent.
- Full PostgreSQL ecosystem (read replicas, PgBouncer, pg_partman) available for free.
- Team already proficient with PostgreSQL.

**Negative / Risks:**

- **Scalability ceiling:** pgvector HNSW has higher memory overhead than purpose-built ANN engines above ~50M vectors. If NeuroFlow grows past this threshold, a migration to Qdrant or Weaviate will be necessary. We will track vector count and set a 40M-vector alert as the migration trigger.
- **Single point of failure:** vectors and relational data share one Postgres instance. Mitigation: streaming replication to a hot standby, automated failover via Patroni.
- **No multi-tenant index isolation:** all chunks share one table; tenant isolation is via `WHERE user_id = ?` row-level security. Pinecone namespaces would be simpler. Mitigation: RLS policies enforced at the application connection pool level.
- **Re-indexing cost:** changing the embedding model requires re-embedding all chunks and rebuilding the HNSW index, which is a write-heavy operation. Mitigation: maintain a `model_version` column; support multiple active embeddings during migration windows.

**Migration Path:**

If we cross 40M vectors or observe p95 ANN latency above 100ms sustained over one week, we will evaluate Qdrant as the primary migration target (sparse vector support, Rust performance, clean REST API) and build an extraction pipeline from pgvector to Qdrant with dual-write for zero-downtime migration.
