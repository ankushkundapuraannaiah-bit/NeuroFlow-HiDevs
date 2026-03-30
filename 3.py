import asyncio
from typing import Dict, Any, Tuple
from pipelines.retrieval.retrieval_pipeline import RetrievalPipeline
from .generator import StreamingGenerator

class GenerationPipeline:
    def __init__(self, db_connection_string: str, openai_api_key: str, redis_client):
        self.retrieval = RetrievalPipeline(db_connection_string, openai_api_key)
        self.generator = StreamingGenerator(openai_api_key, redis_client)
    
    async def generate(self, query: str, stream: bool = True, pipeline_id: str = None) -> Tuple[str, Dict[str, Any]]:
        """Full pipeline: retrieval -> generation"""
        
        # 1. Retrieve
        context, context_metadata, retrieval_results = await self.retrieval.retrieve(query)
        
        if stream:
            # For streaming, return generator
            async def stream_gen():
                query_type = "factual"  # From query processor
                async for token in self.generator.generate(
                    query, context, query_type, context_metadata, pipeline_id
                ):
                    yield token
            
            return stream_gen(), {
                "retrieval": {
                    "chunk_count": len(context_metadata.get("chunks_used", [])),
                    "sources": context_metadata.get("sources", []),
                    "total_tokens": context_metadata.get("total_tokens", 0)
                }
            }
        else:
            # Non-streaming: collect full response
            query_type = "factual"
            full_response = ""
            async for token in self.generator.generate(
                query, context, query_type, context_metadata, pipeline_id
            ):
                full_response += token
            
            return full_response, {
                "retrieval": context_metadata,
                "generation": full_response
            }