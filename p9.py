@router.post("/ingest")
async def ingest_documents(
    documents: List[Dict],
    request: Request,
    bp: Backpressure = Depends()
):
    backpressure = await bp.check_ingestion_backpressure()
    
    if backpressure["status_code"] == 503:
        raise HTTPException(
            503,
            detail=backpressure["error"],
            headers={"Retry-After": str(backpressure["retry_after"])}
        )
    
    # Enqueue documents
    for doc in documents:
        await arq.enqueue_job("process_document", doc)
    
    if backpressure["status_code"] == 202:
        response = JSONResponse(
            status_code=202,
            content={"message": "queued", **backpressure}
        )
    else:
        response = JSONResponse(status_code=200, content={"message": "queued"})
    
    return response