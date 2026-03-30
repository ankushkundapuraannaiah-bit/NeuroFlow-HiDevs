async def generate_with_sse(self, query: str, context: str, query_type: str, 
                          context_metadata: Dict[str, Any], pipeline_run_id: str, redis: aioredis.Redis) -> None:
    """Generation that updates Redis for SSE consumption"""
    
    # Update retrieval complete
    await redis.hset(f"pipeline_run:{pipeline_run_id}", "status", "retrieval_complete")
    await redis.hset(f"pipeline_run:{pipeline_run_id}", "retrieval_metadata", json.dumps(context_metadata))
    
    full_response = ""
    token_buffer = []
    
    # ... (existing generation code) ...
    
    # During streaming, update Redis with tokens
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            delta = chunk.choices[0].delta.content
            full_response += delta
            token_buffer.append(delta)
            
            # Update Redis with latest tokens (batch every 10 tokens)
            if len(token_buffer) >= 10:
                await redis.hset(f"pipeline_run:{pipeline_run_id}", "token_stream", json.dumps(token_buffer))
                token_buffer = []
    
    # Final token flush
    if token_buffer:
        await redis.hset(f"pipeline_run:{pipeline_run_id}", "token_stream", json.dumps(token_buffer))