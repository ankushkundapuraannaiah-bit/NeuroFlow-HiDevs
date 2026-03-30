import asyncio
import openai
from typing import List
from sentence_transformers import CrossEncoder
from .retriever import RetrievalResult

class Reranker:
    def __init__(self, use_local_model: bool = False, openai_api_key: str = None):
        self.use_local_model = use_local_model
        if use_local_model:
            self.model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        else:
            openai.api_key = openai_api_key
    
    async def rerank(self, query: str, candidates: List[RetrievalResult], top_k: int = 10) -> List[RetrievalResult]:
        """Rerank top candidates using cross-encoder"""
        
        if self.use_local_model:
            return await self._local_rerank(query, candidates, top_k)
        else:
            return await self._api_rerank(query, candidates, top_k)
    
    async def _api_rerank(self, query: str, candidates: List[RetrievalResult], top_k: int) -> List[RetrievalResult]:
        """Parallel API calls to LLM for relevance scoring"""
        
        async def score_pair(idx: int) -> tuple:
            prompt = f"Rate the relevance of this passage to the query on a scale of 0-10.\nQuery: {query}\nPassage: {candidates[idx].content}\nScore:"
            
            try:
                response = await openai.ChatCompletion.acreate(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=5,
                    temperature=0.1
                )
                score = float(response.choices[0].message.content.strip())
                return idx, max(0, min(10, score)) / 10.0  # Normalize to 0-1
            except:
                return idx, 0.5  # Fallback score
        
        # Score all candidates in parallel
        tasks = [score_pair(i) for i in range(len(candidates))]
        scored = await asyncio.gather(*tasks)
        
        # Sort by score
        scored.sort(key=lambda x: -x[1])
        
        return [
            RetrievalResult(
                chunk_id=candidates[idx].chunk_id,
                content=candidates[idx].content,
                score=score,
                metadata=candidates[idx].metadata,
                rank=i+1
            )
            for i, (idx, score) in enumerate(scored[:top_k])
        ]
    
    async def _local_rerank(self, query: str, candidates: List[RetrievalResult], top_k: int) -> List[RetrievalResult]:
        """Local cross-encoder reranking"""
        pairs = [(query, cand.content) for cand in candidates]
        scores = self.model.predict(pairs)
        
        scored = sorted(
            [(i, score) for i, score in enumerate(scores)],
            key=lambda x: -x[1]
        )
        
        return [
            RetrievalResult(
                chunk_id=candidates[idx].chunk_id,
                content=candidates[idx].content,
                score=score,
                metadata=candidates[idx].metadata,
                rank=i+1
            )
            for i, (idx, score) in enumerate(scored[:top_k])
        ]