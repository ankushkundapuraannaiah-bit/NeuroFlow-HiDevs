import asyncio
from typing import List, Tuple
from .retriever import HybridRetriever
from .fusion import reciprocal_rank_fusion
from .reranker import Reranker
from .context_assembler import ContextAssembler
from .retriever import RetrievalResult

class RetrievalPipeline:
    def __init__(self, db_connection_string: str, openai_api_key: str):
        self.retriever = HybridRetriever(db_connection_string)
        self.reranker = Reranker(openai_api_key=openai_api_key)
        self.assembler = ContextAssembler()
    
    async def retrieve(self, query: str, k: int = 10) -> Tuple[str, dict, List[RetrievalResult]]:
        # Step 1: Retrieve top-40 candidates
        raw_results = await self.retriever.retrieve(query, k=40)
        
        # Step 2: RRF fusion
        fused_results = reciprocal_rank_fusion([raw_results])
        
        # Step 3: Cross-encoder reranking
        reranked = await self.reranker.rerank(query, fused_results[:40], top_k=k)
        
        # Step 4: Context assembly
        context, metadata = self.assembler.assemble(reranked, k=k)
        
        return context, metadata, reranked