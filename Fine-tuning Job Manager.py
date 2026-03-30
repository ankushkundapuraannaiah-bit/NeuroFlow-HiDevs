import asyncio
import json
import uuid
import arq
from openai import AsyncOpenAI
from pathlib import Path
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from blackbox.core.model_router import ModelRouter
from blackbox.db.models import FinetuneJob
from .extractor import extract_training_pairs, format_training_jsonl
from .tracker import MLflowTracker

class FinetuneJobManager:
    def __init__(self, openai_client: AsyncOpenAI, db: AsyncSession):
        self.client = openai_client
        self.db = db
        self.tracker = MLflowTracker()
    
    async def submit_job(self, base_model: str = "gpt-4o-mini") -> Dict[str, Any]:
        """Full fine-tuning job submission."""
        job_id = uuid.uuid4()
        
        # 1. Extract training pairs
        pairs = await extract_training_pairs(self.db, job_id=job_id)
        if not pairs:
            raise ValueError("No valid training pairs found")
        
        # 2. Write JSONL
        jsonl_path = Path(f"training_data/{job_id}.jsonl")
        jsonl_path.parent.mkdir(exist_ok=True)
        
        jsonl_lines = format_training_jsonl(pairs)
        with open(jsonl_path, 'w') as f:
            f.write('\n'.join(jsonl_lines) + '\n')
        
        # 3. Start MLflow tracking
        date_range = "2024-01-01 to 2024-12-31"  # From pairs metadata
        mlflow_run_id = self.tracker.start_training_job(
            job_id, pairs, base_model, date_range
        )
        
        # 4. Submit to OpenAI
        file_resp = await self.client.files.create(
            file=open(jsonl_path, "rb"), 
            purpose="fine-tune"
        )
        
        job = await self.client.fine_tuning.jobs.create(
            training_file=file_resp.id, 
            model=base_model,
            hyperparameters={"n_epochs": 3}
        )
        
        # 5. Record job
        finetune_job = FinetuneJob(
            id=job_id,
            provider_job_id=job.id,
            base_model=base_model,
            status="queued",
            mlflow_run_id=mlflow_run_id,
            training_file_id=file_resp.id,
            pair_count=len(pairs),
            created_at=datetime.utcnow()
        )
        self.db.add(finetune_job)
        await self.db.commit()
        
        # 6. Schedule status polling
        await arq.enqueue_job("poll_finetune_status", job_id, job.id)
        
        return {
            "job_id": str(job_id),
            "provider_job_id": job.id,
            "status": "queued",
            "pairs_extracted": len(pairs),
            "mlflow_run_id": mlflow_run_id
        }

async def poll_finetune_status(ctx, job_id: uuid.UUID, provider_job_id: str):
    """ARQ cron job to poll OpenAI fine-tuning status."""
    client = AsyncOpenAI()
    db = ctx['db']
    router = ModelRouter()
    
    job = await client.fine_tuning.jobs.retrieve(provider_job_id)
    
    # Update status
    finetune_job = await db.get(FinetuneJob, job_id)
    finetune_job.status = job.status
    
    if job.status == "succeeded":
        # Register fine-tuned model
        fine_tuned_model = job.fine_tuned_model
        router.register_model(
            model_name=fine_tuned_model,
            task_types=["rag_generation"],
            prefer_fine_tuned=True
        )
        
        finetune_job.fine_tuned_model = fine_tuned_model
        
        # Log final metrics to MLflow
        tracker = MLflowTracker()
        tracker.log_training_results(
            finetune_job.mlflow_run_id,
            job.training_loss_final or 0.0,
            job.validation_loss_final or 0.0,
            job.trained_tokens
        )
    
    await db.commit()