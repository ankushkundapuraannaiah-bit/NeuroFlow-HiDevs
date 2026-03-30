import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from blackbox.db.models import TrainingPair, PipelineRun, Evaluation
from evaluation.judge import EvaluationJudge
from blackbox.core.tokenizer import get_tokenizer

PII_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b|'  # emails
    r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b|'                          # US phones
    r'\b\d{3}-\d{2}-\d{4}\b'                                   # SSN-like
)

async def extract_training_pairs(
    db: AsyncSession,
    quality_threshold: float = 0.82,
    job_id: uuid.UUID = None
) -> List[Dict[str, Any]]:
    """Extract high-quality training pairs for fine-tuning."""
    
    # Query eligible pairs
    stmt = select(TrainingPair).join(
        PipelineRun, TrainingPair.run_id == PipelineRun.id
    ).join(
        Evaluation, TrainingPair.run_id == Evaluation.run_id
    ).where(
        and_(
            Evaluation.overall_score >= quality_threshold,
            TrainingPair.included_in_job.is_(None),
            or_(
                PipelineRun.user_rating >= 4,
                PipelineRun.user_rating.is_(None)
            )
        )
    )
    
    result = await db.execute(stmt)
    pairs = result.scalars().all()
    
    validated_pairs = []
    judge = EvaluationJudge(db)
    tokenizer = get_tokenizer()
    
    for pair in pairs:
        if await _validate_training_pair(
            db, judge, tokenizer, pair.query, pair.answer, pair.context
        ):
            validated_pairs.append({
                "training_pair_id": str(pair.id),
                "query": pair.query,
                "answer": pair.answer,
                "context": pair.context
            })
            
            # Mark as included
            pair.included_in_job = job_id
    
    await db.commit()
    return validated_pairs

async def _validate_training_pair(
    db: AsyncSession,
    judge: EvaluationJudge,
    tokenizer,
    query: str,
    answer: str,
    context: str
) -> bool:
    """Validate single training pair."""
    
    # 1. PII check
    if PII_REGEX.search(query):
        return False
    
    # 2. Token length (50-2000 tokens)
    answer_tokens = len(tokenizer.encode(answer))
    if not (50 <= answer_tokens <= 2000):
        return False
    
    # 3. Contains citation
    if not re.search(r'\$Source \d+\$', answer):
        return False
    
    # 4. Faithfulness > 0.8 (chunks=[] since we already have context)
    metrics = await judge.evaluate(0, query, answer, context, [])
    if metrics["faithfulness"] < 0.8:
        return False
    
    return True

def format_training_jsonl(pairs: List[Dict], system_prompt: str = "You are a precise research assistant...") -> List[str]:
    """Format pairs as OpenAI fine-tuning JSONL."""
    jsonl_lines = []
    
    for pair in pairs:
        formatted = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user", 
                    "content": f"[Context]\n{pair['context']}\n\n[Question]\n{pair['query']}"
                },
                {"role": "assistant", "content": pair["answer"]}
            ]
        }
        jsonl_lines.append(json.dumps(formatted))
    
    return jsonl_lines