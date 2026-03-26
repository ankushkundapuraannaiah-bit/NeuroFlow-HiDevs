# NeuroFlow-HiDevs

**NeuroFlow** is a production-grade Retrieval-Augmented Generation (RAG) platform with automated evaluation and continuous fine-tuning. It ingests multi-modal documents, serves hybrid retrieval, streams LLM generations, scores every response, and progressively improves via feedback-driven fine-tuning.

---

## Repository Structure

```
NeuroFlow-HiDevs/
├── backend/          # FastAPI application — ingestion, retrieval, generation endpoints
├── frontend/         # React/Next.js UI — chat interface, pipeline config, eval dashboard
├── pipelines/        # Apache Airflow / Prefect DAGs for ingestion and fine-tuning workflows
├── evaluation/       # Evaluation harness, metric definitions, LLM-as-judge prompts
├── infra/            # Terraform, Docker Compose, Kubernetes manifests
├── docs/
│   ├── architecture.md     # System design for all five subsystems
│   ├── api-contracts.md    # Full REST API specification
│   ├── data-models.md      # Database schemas and vector store models
│   └── adr/
│       ├── 001-vector-store.md
│       ├── 002-chunking-strategy.md
│       └── 003-evaluation-framework.md
└── README.md
```

---

## Subsystems

| Subsystem | Responsibility |
|-----------|---------------|
| **Ingestion** | Accept PDF/DOCX/images/CSV/URLs → extract → chunk → embed → store |
| **Retrieval** | Hybrid search (dense + sparse) → RRF fusion → cross-encoder reranking |
| **Generation** | Prompt assembly → LLM routing → streaming → logging |
| **Evaluation** | Async scoring on faithfulness, relevance, precision, recall |
| **Fine-Tuning** | Extract high-quality pairs → JSONL → fine-tune jobs → model routing |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/<your-username>/NeuroFlow-HiDevs.git
cd NeuroFlow-HiDevs

# 2. Environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start services
docker compose up -d

# 4. Run backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# 5. Run frontend
cd frontend
npm install && npm run dev
```

---

## Documentation

- [Architecture](docs/architecture.md) — subsystem design and data flow diagrams
- [API Contracts](docs/api-contracts.md) — full REST API reference
- [ADR: Vector Store](docs/adr/001-vector-store.md)
- [ADR: Chunking Strategy](docs/adr/002-chunking-strategy.md)
- [ADR: Evaluation Framework](docs/adr/003-evaluation-framework.md)

---

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy, pgvector
- **LLMs**: OpenAI GPT-4o, Anthropic Claude 3.5, Mistral (routed by cost/capability)
- **Embeddings**: text-embedding-3-large (OpenAI), fallback to local BGE
- **Vector Store**: PostgreSQL + pgvector
- **Evaluation**: Custom LLM-as-judge + RAGAS-inspired metrics
- **Experiment Tracking**: MLflow
- **Infrastructure**: Docker, Kubernetes, Terraform

---

## Branch Strategy

- `main` — stable, deployable
- `task-*` — feature branches per sprint task
- Current branch: `task-31`

---

## License

MIT
