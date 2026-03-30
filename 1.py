import asyncio
import json
from typing import List
from blackbox.core.llm import ModelRouter
from blackbox.core.embeddings import EmbeddingClient
import numpy as np

async def evaluate_faithfulness(query: str, answer: str, context: str) -> float:
    """Evaluate if all claims in answer are grounded in context."""
    if not answer.strip():
        return 1.0
    
    router = ModelRouter(task_type="evaluation")
    
    # Extract claims
    claim_prompt = f"""
    Extract all factual claims from this answer as a JSON array of strings.
    A claim is any verifiable statement about the world.
    Answer ONLY with valid JSON array.

    Answer: {answer}
    """
    
    claims_response = await router.acompletion(claim_prompt)
    try:
        claims = json.loads(claims_response.strip('```json').strip('```'))
        if not isinstance(claims, list) or not claims:
            return 0.0
    except:
        return 0.0
    
    if not context.strip():
        return 0.0
    
    # Parallel verification of claims
    async def verify_claim(claim: str) -> float:
        verify_prompt = f"""
        Is this claim ENTIRELY supported by the context? Answer ONLY: yes/no/partial
        
        Claim: {claim}
        Context: {context}
        """
        response = await router.acompletion(verify_prompt)
        if "yes" in response.lower():
            return 1.0
        elif "partial" in response.lower():
            return 0.5
        return 0.0
    
    scores = await asyncio.gather(*[verify_claim(claim) for claim in claims])
    return np.mean(scores).item()