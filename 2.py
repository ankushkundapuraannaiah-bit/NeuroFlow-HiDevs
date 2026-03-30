from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import uuid
import asyncio
import aioredis
import json
from typing import Optional
from pipelines.generation.generation_pipeline import GenerationPipeline

router = APIRouter()
redis_client = None  # Initialize in app startup

@router.post("/query")
async def query_endpoint(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks
):
    """Main query endpoint"""
    query = request.get("query")
    stream = request.get("stream", True)
    pipeline_id = str(uuid.uuid4())
    
    if not query:
        raise HTTPException(status_code=400, detail="Query required")
    
    pipeline = GenerationPipeline("your_db", "your_openai_key", redis_client)
    
    # Log pipeline run start
    await redis_client.hset(f"pipeline_run:{pipeline_id}", "status", "retrieval_start")
    await redis_client.hset(f"pipeline_run:{pipeline_id}", "query", query)
    await redis_client.hset(f"pipeline_run:{pipeline_id}", "created_at", str(asyncio.get_event_loop().time()))
    
    if not stream:
        # Non-streaming response
        response, metadata = await pipeline.generate(query, stream=False, pipeline_id=pipeline_id)
        await redis_client.hset(f"pipeline_run:{pipeline_id}", "status", "complete")
        return {
            "run_id": pipeline_id,
            "response": response,
            "metadata": metadata
        }
    
    # Streaming: return run_id immediately, client polls SSE
    return {"run_id": pipeline_id, "stream": True}

@router.get("/query/{run_id}/stream")
async def stream_endpoint(run_id: str):
    """SSE streaming endpoint"""
    
    async def event_generator():
        last_event_time = asyncio.get_event_loop().time()
        keepalive_interval = 15  # seconds
        
        while True:
            # Check if run completed
            run_data = await redis_client.hgetall(f"pipeline_run:{run_id}")
            if not run_data:
                yield {
                    "event": "error",
                    "data": json.dumps({"message": "Run not found"})
                }
                break
            
            status = run_data.get(b"status", b"").decode()
            
            if status == "retrieval_start":
                yield {
                    "event": "retrieval_start",
                    "data": json.dumps({"message": "Starting retrieval..."})
                }
            
            elif status == "retrieval_complete":
                retrieval_data = json.loads(run_data.get(b"retrieval_metadata", b"{}").decode())
                yield {
                    "event": "retrieval_complete",
                    "data": json.dumps({
                        "chunk_count": retrieval_data.get("chunk_count", 0),
                        "sources": retrieval_data.get("sources", [])
                    })
                }
            
            elif "token_stream" in run_data:
                # Send accumulated tokens
                tokens = json.loads(run_data[b"token_stream"].decode())
                for token in tokens[-10:]:  # Last 10 tokens
                    yield {
                        "event": "token",
                        "data": json.dumps({"delta": token})
                    }
            
            elif status == "complete":
                completion = json.loads(run_data[b"completion"].decode())
                citations = completion.get("citations", [])
                
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "run_id": run_id,
                        "full_response": completion["generation"],
                        "citations": citations,
                        "tokens": {
                            "input": completion["input_tokens"],
                            "output": completion["output_tokens"]
                        },
                        "latency_ms": completion["latency_ms"]
                    })
                }
                break
            
            # Keepalive
            current_time = asyncio.get_event_loop().time()
            if current_time - last_event_time > keepalive_interval:
                yield {
                    "event": "keepalive",
                    "data": json.dumps({"timestamp": current_time})
                }
                last_event_time = current_time
            
            await asyncio.sleep(0.1)
    
    return EventSourceResponse(event_generator())