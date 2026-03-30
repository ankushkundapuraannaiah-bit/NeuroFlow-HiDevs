from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from blackbox.db.session import get_db
from blackbox.services.finetune.job_manager import FinetuneJobManager
from pipelines.finetuning.extractor import extract_training_pairs, format_training_jsonl
from blackbox.db.models import FinetuneJob, TrainingPair

router = APIRouter(prefix="/finetune", tags=["finetuning"])

@router.post("/jobs")
async def create_finetune_job(
    base_model: str = "gpt-4o-mini",
    db: AsyncSession = Depends(get_db)
):
    """Trigger full fine-tuning pipeline."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    manager = FinetuneJobManager(client, db)
    
    try:
        result = await manager.submit_job(base_model)
        return result
    except Exception as e:
        raise HTTPException(500, f"Job submission failed: {str(e)}")

@router.get("/jobs")
async def list_finetune_jobs(
    db: AsyncSession = Depends(get_db),
    limit: int = 50
) -> List[Dict]:
    """List all fine-tuning jobs."""
    stmt = select(FinetuneJob).order_by(FinetuneJob.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    
    jobs = []
    for job in result.scalars():
        jobs.append({
            "job_id": str(job.id),
            "status": job.status,
            "base_model": job.base_model,
            "fine_tuned_model": job.fine_tuned_model,
            "pair_count": job.pair_count,
            "provider_job_id": job.provider_job_id,
            "mlflow_run_id": job.mlflow_run_id,
            "created_at": job.created_at.isoformat()
        })
    
    return jobs

@router.get("/jobs/{job_id}")
async def get_finetune_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get detailed job status."""
    job_uuid = uuid.UUID(job_id)
    job = await db.get(FinetuneJob, job_uuid)
    
    if not job:
        raise HTTPException(404, "Job not found")
    
    return {
        "job_id": str(job.id),
        "status": job.status,
        "base_model": job.base_model,
        "fine_tuned_model": job.fine_tuned_model,
        "pair_count": job.pair_count,
        "mlflow_url": f"http://localhost:5000/#/experiments/0/runs/{job.mlflow_run_id}",
        "provider_job_id": job.provider_job_id
    }

@router.get("/training-data/preview")
async def preview_training_data(db: AsyncSession = Depends(get_db)) -> List[Dict]:
    """Preview 5 sample training pairs without submitting job."""
    pairs = await extract_training_pairs(db, job_id=None)[:5]
    
    preview = []
    for pair in pairs:
        jsonl_lines = format_training_jsonl([pair])
        preview.append({
            "query_preview": pair["query"][:200] + "..." if len(pair["query"]) > 200 else pair["query"],
            "answer_preview": pair["answer"][:300] + "...",
            "jsonl_sample": jsonl_lines[0],
            "tokens": len(get_tokenizer().encode(pair["answer"]))
        })
    
    return {"sample_pairs": preview, "total_available": len(pairs)}