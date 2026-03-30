# backend/api/pipelines.py
router = APIRouter(prefix="/pipelines", tags=["pipelines"])

@router.post("/")
async def create_pipeline(
    config: PipelineConfig,
    current_user: TokenPayload = Depends(require_scope("admin")),
    db: AsyncSession = Depends(get_db)
):
    # Protected by admin scope
    pass

@router.post("/query")
async def run_query(
    request: QueryRequest,
    current_user: TokenPayload = Depends(require_scope("query")),  # query scope required
    db: AsyncSession = Depends(get_db)
):
    # Sanitization already handled by middleware
    pass

@router.post("/ingest")
async def ingest_documents(
    documents: List[DocumentRequest],
    current_user: TokenPayload = Depends(require_scope("ingest")),
    db: AsyncSession = Depends(get_db)
):
    for doc in documents:
        # File validation
        if doc.file_content:
            if not validate_file_mimetype(doc.filename, doc.file_content):
                raise HTTPException(400, "Invalid file type")
        
        # Secret redaction
        if doc.content:
            redacted_content, redactions = detect_and_redact_secrets(doc.content)
            if redactions:
                logger.warning("Secrets redacted", extra={"redactions": redactions})
            doc.content = redacted_content
    pass