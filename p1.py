import asyncio
import json
import numpy as np
from blackbox.core.llm import ModelRouter
from blackbox.core.embeddings import EmbeddingClient

async def evaluate_answer_relevance(query: str, answer: str) -> float:
    """Measure how well answer addresses the query."""
    if not answer.strip():
        return 0.0
    
    router = ModelRouter(task_type="evaluation")
    embed_client = EmbeddingClient()
    
    # Generate 4 questions the answer could respond to
    question_prompt = f"""
    Given this answer, generate exactly 4 questions an oracle would ask that this perfectly answers.
    Return ONLY valid JSON array of strings.

    Answer: {answer}
    """
    
    questions_response = await router.acompletion(question_prompt)
    try:
        generated_questions = json.loads(questions_response.strip('```json').strip('```'))
        if not isinstance(generated_questions, list) or len(generated_questions) < 3:
            return 0.0
    except:
        return 0.0
    
    # Embed query and generated questions
    query_embedding = await embed_client.aembed(query)
    question_embeddings = await embed_client.aembed_batch(generated_questions[:4])
    
    # Compute mean cosine similarity
    similarities = [
        np.dot(query_embedding, q_emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(q_emb))
        for q_emb in question_embeddings
    ]
    
    return float(np.mean(similarities))