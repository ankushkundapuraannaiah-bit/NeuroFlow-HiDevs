# ADR 002 — Chunking Strategy

**Status:** Accepted  
**Date:** 2026-03-26  
**Deciders:** Platform Team

---

## Context

Chunking is among the highest-leverage decisions in a RAG pipeline. The chunk size and boundary method directly determine retrieval precision (whether a retrieved chunk answers the question) and recall (whether the right chunks are retrieved at all). Chunks that are too small lose context; chunks that are too large dilute relevance scores and exceed the reranker's input budget.

We evaluated three strategies:

**Fixed-size chunking** splits text every N tokens (e.g., 512) with a configurable overlap (e.g., 50 tokens). It is computationally trivial, completely deterministic, and requires no NLP models. Its fundamental problem is that it is indifferent to semantic boundaries — a fixed window can slice a sentence, split a paragraph mid-thought, or concatenate unrelated ideas from adjacent sections. Retrieval precision suffers because chunks are semantically noisy.

**Sentence-boundary chunking** respects natural language boundaries by splitting at sentence terminators (`.`, `!`, `?`) using a sentence tokenizer (spaCy or NLTK). Sentences are then aggregated into chunks of up to N tokens. This prevents mid-sentence cuts and improves coherence per chunk. It is faster than semantic methods, requires only a sentence tokenizer, and is robust to most prose. Its weakness is that it ignores topic shifts within a sequence of grammatically complete sentences — a paragraph can contain two distinct claims, both of which end up in the same chunk.

**Semantic chunking** uses an embedding model to detect topic shifts between consecutive sentences. Sentences whose adjacent cosine similarity drops below a configurable threshold are treated as a boundary. This produces chunks that are internally coherent and topically homogeneous, which is the best property for retrieval. The tradeoff is higher latency (requires an embedding pass over all sentences during ingestion) and sensitivity to threshold tuning — a threshold that is too high produces micro-chunks; one that is too low merges dissimilar content.

---

## Decision

We will use **semantic chunking as the default strategy**, with automatic fallback to sentence-boundary chunking and fixed-size chunking under specific conditions.

The routing logic is:

```
IF document has > 500 tokens AND has prose content (PDF, DOCX, URL):
    → Semantic chunking (cosine drop threshold: 0.3)
        IF semantic chunking produces > 30% micro-chunks (< 50 tokens):
            → Fall back to sentence-boundary chunking
ELIF document is structured data (CSV, JSON, code):
    → Fixed-size chunking (512 tokens, 64-token overlap)
ELIF document is very short (< 500 tokens):
    → Single chunk (no split)
```

The justification for semantic chunking as default is retrieval quality. In offline evaluation over 200 test queries against a 10,000-chunk corpus, semantic chunks produced context precision 0.71 vs 0.58 for fixed-size and 0.64 for sentence-boundary. The additional ingestion latency (~1.8× vs sentence-boundary) is acceptable because ingestion is an async offline process.

Fixed-size chunking is used for structured data because semantic embeddings of CSV rows or JSON objects are unstable — the model is not trained to detect semantic shifts in tabular content. Fixed-size with overlap works correctly here because rows have uniform information density.

We implement a **chunk overlap** of 10% of chunk size for all strategies to handle cases where an answer spans a chunk boundary.

---

## Consequences

**Positive:**

- Semantic chunks are topically coherent, which directly improves retrieval precision and context recall.
- Automatic fallback ensures robustness to degenerate inputs (very short texts, tables, code).
- The strategy is configurable per pipeline, so future experiments require no code changes.
- Chunk quality metrics (average token count, variance, micro-chunk rate) are logged per ingestion job for monitoring.

**Negative / Risks:**

- **Increased ingestion latency.** Semantic chunking runs an embedding model over all sentences during ingestion. For a 100-page PDF (~50,000 tokens), this adds ~3–5 seconds vs. fixed-size. Acceptable given async ingestion, but must be monitored as corpus size grows.
- **Threshold sensitivity.** The cosine drop threshold of 0.3 was tuned on our test corpus. It may not generalize to all domains (e.g., legal or scientific documents with dense terminology). We will monitor micro-chunk rate in production and allow per-pipeline threshold overrides.
- **Chunking strategy mismatch with reranking.** If the semantic chunker produces variable-length chunks, the cross-encoder reranker receives inputs of varying length. We enforce a hard token cap of 512 tokens per chunk post-chunking to prevent reranker instability.

**Conditions for Switching Strategy:**

We will switch a pipeline's default from semantic to sentence-boundary if its production micro-chunk rate (chunks < 50 tokens) exceeds 25% over a 7-day window, or if semantic chunking ingestion latency causes queue depth to grow faster than it drains.

We will consider **hierarchical chunking** (parent-child) in v2 if context recall metrics show that answers frequently require synthesis across adjacent chunks of the same parent document.
