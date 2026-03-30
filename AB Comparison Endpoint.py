from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import asyncio
from backend.db.session import get_db
from backend.services.pipeline_runner import PipelineRunner
from backend.services.evaluator import EvaluationJudge
import time

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

@router.post("/compare")
async def compare_pipelines(
    comparison: Dict[str, Any],
    db: AsyncSession = Depends(get_db)
):
    """Run A/B comparison between two pipelines."""
    query = comparison["query"]
    pipeline_a_id = uuid.UUID(comparison["pipeline_a_id"])
    pipeline_b_id = uuid.UUID(comparison["pipeline_b_id"])
    
    runner = PipelineRunner(db)
    judge = EvaluationJudge(db)
    
    start_time = time.time()
    
    # Run both pipelines in parallel
    a_task, b_task = asyncio.gather(
        runner.run_pipeline(pipeline_a_id, query),
        runner.run_pipeline(pipeline_b_id, query),
        return_exceptions=True
    )
    
    a_result, b_result = await a_task, await b_task
    
    if isinstance(a_result, Exception):
        raise HTTPException(500, f"Pipeline A failed: {a_result}")
    if isinstance(b_result, Exception):
        raise HTTPException(500, f"Pipeline B failed: {b_result}")
    
    # Enqueue evaluations
    eval_a_task = judge.evaluate(
        a_result["run_id"],
        query,
        a_result["answer"],
        a_result["context"],
        a_result["chunks"]
    )
    eval_b_task = judge.evaluate(
        b_result["run_id"],
        query,
        b_result["answer"],
        b_result["context"],
        b_result["chunks"]
    )
    
    await asyncio.gather(eval_a_task, eval_b_task)
    
    total_time = (time.time() - start_time) * 1000
    
    return {
        "query": query,
        "total_comparison_time_ms": total_time,
        "pipeline_a": {
            "run_id": str(a_result["run_id"]),
            "generation": a_result["answer"][:200] + "..." if len(a_result["answer"]) > 200 else a_result["answer"],
            "retrieval_latency_ms": a_result["retrieval_latency_ms"],
            "total_latency_ms": a_result["total_latency_ms"],
            "chunks_used": len(a_result["chunks"]),
            "input_tokens": a_result["input_tokens"],
            "output_tokens": a_result["output_tokens"]
        },
        "pipeline_b": {
            "run_id": str(b_result["run_id"]),
            "generation": b_result["answer"][:200] + "..." if len(b_result["answer"]) > 200 else b_result["answer"],
            "retrieval_latency_ms": b_result["retrieval_latency_ms"],
            "total_latency_ms": b_result["total_latency_ms"],
            "chunks_used": len(b_result["chunks"]),
            "input_tokens": b_result["input_tokens"],
            "output_tokens": b_result["output_tokens"]
        }
    }