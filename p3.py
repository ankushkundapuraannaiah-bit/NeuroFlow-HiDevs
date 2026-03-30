import asyncio
import re
from blackbox.core.llm import ModelRouter
from typing import List

async def evaluate_context_recall(query: str, chunks: List[str], answer: str) -> float:
    """Measure if answer sentences can be attributed to retrieved context."""
    if not answer.strip():
        return 0.0
    
    # Simple sentence splitting
    sentences = re.split(r'[.!?]+', answer)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    
    if not sentences:
        return 0.0
    
    router = ModelRouter(task_type="evaluation")
    context = "\n\n".join(chunks)
    
    async def is_attributable(sentence: str) -> float:
        prompt = f"""
        Can this sentence be directly attributed to/derived from the provided context?
        Answer ONLY: yes/no
        
        Sentence: {sentence}
        Context: {context}
        """
        response = await router.acompletion(prompt)
        return 1.0 if "yes" in response.lower() else 0.0
    
    scores = await asyncio.gather(*[is_attributable(s) for s in sentences])
    return float(sum(scores) / len(scores))