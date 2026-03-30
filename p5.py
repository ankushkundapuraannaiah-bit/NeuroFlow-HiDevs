from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from blackbox.db.session import get_db
from blackbox.db.models import Evaluation
from evaluation.judge import EvaluationJudge
import datetime

router = APIRouter()

@router.patch("/{run_id}/rating")
async def update_run_rating(
    run_id: int,
    rating_data: dict,
    db: AsyncSession = Depends(get_db)
):
    """Update human rating for evaluation calibration."""
    rating = rating_data.get("rating")
    if not 1 <= rating <= 5:
        raise HTTPException(400, "Rating must be 1-5")
    
    # Update evaluation record
    eval_record = await db.execute(
        select(Evaluation).where(Evaluation.run_id == run_id)
    )
    eval_record = eval_record.scalar_one_or_none()
    
    if not eval_record:
        raise HTTPException(404, "Evaluation not found")
    
    eval_record.user_rating = rating
    eval_record.user_rated_at = datetime.utcnow()
    
    # Check calibration drift
    normalized_human = rating / 5.0
    drift = abs(eval_record.overall_score - normalized_human)
    
    if drift > 0.3:
        eval_record.metadata = {**eval_record.metadata, "calibration_needed": True}
    
    await db.commit()
    return {"status": "updated", "drift": drift}