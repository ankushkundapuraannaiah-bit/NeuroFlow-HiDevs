import asyncio
import json
import numpy as np
from opentelemetry import trace
from sqlalchemy.ext.asyncio import AsyncSession
from blackbox.db.models import Evaluation, PipelineRun, TrainingPair
from blackbox.core.llm import ModelRouter
from .metrics.faithfulness import evaluate_faithfulness
from .metrics.answer_relevance import evaluate_answer_relevance
from .metrics.context_precision import evaluate_context_precision
from .metrics.context_recall import evaluate_context_recall

class EvaluationJudge:
    WEIGHTS = {
        "faithfulness": 0.35,
        "answer_relevance": 0.30,
        "context_precision": 0.20,
        "context_recall": 0.15
    }
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.tracer = trace.get_tracer(__name__)
    
    async def evaluate(
        self,
        run_id: int,
        query: str,
        answer: str,
        context: str,
        chunks: list[str]
    ) -> dict:
        """Run full evaluation pipeline."""
        with self.tracer.start_as_current_span("evaluation.judge") as span:
            span.set_attribute("run_id", run_id)
            
            start_time = asyncio.get_event_loop().time()
            
            # Parallel metric computation
            faithfulness_task = evaluate_faithfulness(query, answer, context)
            relevance_task = evaluate_answer_relevance(query, answer)
            precision_task = evaluate_context_precision(query, chunks, answer)
            recall_task = evaluate_context_recall(query, chunks, answer)
            
            metrics = await asyncio.gather(
                faithfulness_task,
                relevance_task,
                precision_task,
                recall_task
            )
            
            end_time = asyncio.get_event_loop().time()
            span.set_attribute("total_time_ms", (end_time - start_time) * 1000)
            
            # Set span attributes
            names = ["faithfulness", "answer_relevance", "context_precision", "context_recall"]
            for name, score in zip(names, metrics):
                span.set_attribute(f"metric.{name}", score)
            
            # Compute overall score
            overall_score = np.average(metrics, weights=list(self.WEIGHTS.values()))
            
            result = {
                "faithfulness": float(metrics[0]),
                "answer_relevance": float(metrics[1]),
                "context_precision": float(metrics[2]),
                "context_recall": float(metrics[3]),
                "overall_score": float(overall_score),
                "run_id": run_id
            }
            
            # Persist to database
            await self._persist_evaluation(run_id, result)
            
            # Mark as training candidate if high quality
            if overall_score > 0.8:
                await self._mark_training_candidate(run_id, query, answer, context)
            
            return result
    
    async def _persist_evaluation(self, run_id: int, metrics: dict):
        """Write evaluation to database."""
        eval_record = Evaluation(
            run_id=run_id,
            faithfulness=metrics["faithfulness"],
            answer_relevance=metrics["answer_relevance"],
            context_precision=metrics["context_precision"],
            context_recall=metrics["context_recall"],
            overall_score=metrics["overall_score"],
            created_at=datetime.utcnow()
        )
        self.db.add(eval_record)
        await self.db.commit()
    
    async def _mark_training_candidate(self, run_id: int, query: str, answer: str, context: str):
        """Mark high-quality run as training candidate."""
        training_pair = TrainingPair(
            run_id=run_id,
            query=query,
            answer=answer,
            context=context,
            source="auto_evaluated",
            created_at=datetime.utcnow()
        )
        self.db.add(training_pair)
        await self.db.commit()