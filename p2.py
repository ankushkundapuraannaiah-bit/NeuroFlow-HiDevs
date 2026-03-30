import asyncio
import numpy as np
from blackbox.core.llm import ModelRouter
from typing import List

async def evaluate_context_precision(query: str, chunks: List[str], answer: str) -> float:
    """Measure if retrieved chunks were actually useful."""
    if not chunks:
        return 0.0
    
    router = ModelRouter(task_type="evaluation")
    
    async def is_useful(chunk: str, rank: int) -> float:
        prompt = f"""
        Was this passage useful for generating the answer to the query? Answer ONLY: yes/no
        
        Query: {query}
        Answer: {answer}
        Passage: {chunk}
        """
        response = await router.acompletion(prompt)
        weight = 1.0 / (rank + 1)  # Earlier chunks get higher weight
        return 1.0 * weight if "yes" in response.lower() else 0.0
    
    # Parallel evaluation
    weighted_scores = await asyncio.gather(
        *[is_useful(chunk, i+1) for i, chunk in enumerate(chunks)]
    )
    
    # Harmonic weighting
    total_weight = sum(1.0 / (i+1) for i in range(len(chunks)))
    return sum(weighted_scores) / total_weight if total_weight > 0 else 0.0