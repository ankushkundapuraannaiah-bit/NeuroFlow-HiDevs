import asyncio
import openai
import time
import uuid
import json
import aioredis
from typing import AsyncGenerator, Dict, Any, List, Optional
from contextlib import asynccontextmanager
from .prompt_builder import PromptBuilder
from .citations import CitationParser, Citation
from pipelines.retrieval.retrieval_pipeline import RetrievalPipeline

class GenerationLogger:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def log_prompt(self, pipeline_run_id: str, prompt: Dict[str, str]):
        await self.redis.hset(f"pipeline_run:{pipeline_run_id}", "prompt", json.dumps(prompt))
    
    async def log_completion(self, pipeline_run_id: str, generation: str, 
                           input_tokens: int, output_tokens: int, 
                           model_used: str, latency_ms: float, citations: List[Citation]):
        completion_data = {
            "generation": generation,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model_used": model_used,
            "latency_ms": latency_ms,
            "citations": [c.__dict__ for c in citations],
            "status": "complete",
            "completed_at": time.time()
        }
        await self.redis.hset(f"pipeline_run:{pipeline_run_id}", "completion", json.dumps(completion_data))

class StreamingGenerator:
    def __init__(self, openai_api_key: str, redis_client):
        openai.api_key = openai_api_key
        self.logger = GenerationLogger(redis_client)
        self.prompt_builder = PromptBuilder()
    
    async def generate(self, query: str, context: str, query_type: str, 
                      context_metadata: Dict[str, Any], pipeline_run_id: str) -> AsyncGenerator[str, None]:
        """Streaming generation with logging and citation parsing"""
        
        # Log prompt before generation
        prompt = self.prompt_builder.build(query, context, query_type, context_metadata)
        await self.logger.log_prompt(pipeline_run_id, {
            "system": prompt.system,
            "user": prompt.user
        })
        
        full_response = ""
        start_time = time.time()
        
        # Count input tokens
        input_tokens = len(prompt.system) + len(prompt.user)
        
        try:
            stream = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user}
                ],
                stream=True,
                temperature=0.1,
                max_tokens=2000
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    full_response += delta
                    yield delta  # Stream token-by-token
            
            output_tokens = len(full_response)
            latency_ms = (time.time() - start_time) * 1000
            
            # Parse citations
            chunks_used = context_metadata.get("chunks_used", [])
            citations = CitationParser.parse_response(full_response, chunks_used)
            
            # Log completion
            await self.logger.log_completion(
                pipeline_run_id, full_response, input_tokens, 
                output_tokens, "gpt-3.5-turbo", latency_ms, citations
            )
            
            # Enqueue evaluation job (fire-and-forget)
            await self._enqueue_evaluation(pipeline_run_id, query, full_response, citations)
            
        except Exception as e:
            await self.logger.log_completion(
                pipeline_run_id, str(e), input_tokens, 0, 
                "gpt-3.5-turbo", (time.time() - start_time) * 1000, []
            )
            yield f"Error: {str(e)}"
    
    async def _enqueue_evaluation(self, run_id: str, query: str, response: str, citations: List[Citation]):
        """Fire-and-forget evaluation job"""
        redis = self.logger.redis
        await redis.lpush("evaluation_queue", json.dumps({
            "run_id": run_id,
            "query": query,
            "response": response,
            "citations": [c.__dict__ for c in citations]
        }))