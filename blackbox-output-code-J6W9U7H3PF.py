import asyncio
import asyncpg
from typing import List, Optional
from dataclasses import dataclass
import numpy as np
from .query_processor import ProcessedQuery

@dataclass
class RetrievalResult:
    chunk_id: str
    content: str
    score: float
    metadata: dict
    rank: int

class HybridRetriever:
    def __init__(self, db_connection_string: str):
        self.db_connection_string = db_connection_string
    
    async def retrieve(self, query: str, k: int = 20) -> List[RetrievalResult]:
        processed = await QueryProcessor("").process(query)  # You'll inject API key
        
        # Parallel retrieval for original + expansions
        all_dense_tasks = [self._dense_retrieval(q, k) for q in [query] + processed.expansions]
        all_sparse_tasks = [self._sparse_retrieval(q, k) for q in [query] + processed.expansions]
        
        dense_results = await asyncio.gather(*all_dense_tasks)
        sparse_results = await asyncio.gather(*all_sparse_tasks)
        metadata_results = await self._metadata_retrieval(processed.metadata_filters, query, k)
        
        # Flatten and fuse
        all_results = [item for sublist in dense_results + [metadata_results] for item in sublist]
        fused = await self._fuse_results(all_results)
        
        return fused[:k]
    
    async def _dense_retrieval(self, query: str, k: int) -> List[RetrievalResult]:
        query_embedding = await self._get_query_embedding(query)
        
        async with asyncpg.connect(self.db_connection_string) as conn:
            rows = await conn.fetch(
                """
                SELECT chunk_id, content, embedding <=> $1 as distance, metadata
                FROM chunks 
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> $1
                LIMIT $2
                """,
                query_embedding, k
            )
        
        return [
            RetrievalResult(
                chunk_id=row['chunk_id'],
                content=row['content'],
                score=1.0 - float(row['distance']),  # Convert distance to similarity
                metadata=row['metadata'],
                rank=i+1
            )
            for i, row in enumerate(rows)
        ]
    
    async def _sparse_retrieval(self, query: str, k: int) -> List[RetrievalResult]:
        async with asyncpg.connect(self.db_connection_string) as conn:
            rows = await conn.fetch(
                """
                SELECT chunk_id, content, ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', $1)) as rank_score, metadata
                FROM chunks 
                WHERE to_tsvector('english', content) @@ plainto_tsquery('english', $1)
                ORDER BY ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', $1)) DESC
                LIMIT $2
                """,
                query, k
            )
        
        return [
            RetrievalResult(
                chunk_id=row['chunk_id'],
                content=row['content'],
                score=float(row['rank_score']),
                metadata=row['metadata'],
                rank=i+1
            )
            for i, row in enumerate(rows)
        ]
    
    async def _metadata_retrieval(self, filters: dict, query: str, k: int) -> List[RetrievalResult]:
        if not filters:
            return []
        
        filter_json = filters
        query_embedding = await self._get_query_embedding(query)
        
        async with asyncpg.connect(self.db_connection_string) as conn:
            rows = await conn.fetch(
                """
                SELECT chunk_id, content, embedding <=> $2 as distance, metadata
                FROM chunks 
                WHERE metadata @> $1 AND embedding IS NOT NULL
                ORDER BY embedding <=> $2
                LIMIT $3
                """,
                filter_json, query_embedding, k
            )
        
        return [
            RetrievalResult(
                chunk_id=row['chunk_id'],
                content=row['content'],
                score=1.0 - float(row['distance']),
                metadata=row['metadata'],
                rank=i+1
            )
            for i, row in enumerate(rows)
        ]
    
    async def _get_query_embedding(self, query: str) -> List[float]:
        # Placeholder - implement your embedding model (OpenAI, SentenceTransformers, etc.)
        # For now, return dummy embedding
        return [0.1] * 1536  # OpenAI embedding dimension