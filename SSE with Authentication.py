from sse_starlette.sse import EventSourceResponse
from blackbox.security.auth import verify_token

@router.get("/stream")
async def evaluation_stream(
    request: Request,
    token: str = Header(None, alias="Authorization"),
    redis_client: aioredis.Redis = Depends(get_redis)
):
    if not token or not token.startswith("Bearer "):
        raise HTTPException(401, "Authorization header required")
    
    # Verify token
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token.replace("Bearer ", ""))
    user = await verify_token(credentials)
    
    # Redis pub/sub
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("evaluations:new")
    
    async def event_generator():
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield {
                        "event": "evaluation",
                        "data": json.dumps(data)
                    }
        finally:
            await pubsub.unsubscribe()
    
    return EventSourceResponse(event_generator())