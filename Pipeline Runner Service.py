class PipelineRunner:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def run_pipeline(self, pipeline_id: uuid.UUID, query: str) -> dict:
        """Execute pipeline using specific version config."""
        # Get latest active version
        version_stmt = select(PipelineVersionModel).join(
            Pipeline,
            PipelineVersionModel.pipeline_id == Pipeline.id
        ).where(
            and_(
                Pipeline.id == pipeline_id,
                PipelineVersionModel.status == "active",
                Pipeline.status == "active"
            )
        ).order_by(PipelineVersionModel.version.desc()).limit(1)
        
        version = await self.db.execute(version_stmt)
        version = version.scalar_one_or_none()
        
        if not version:
            raise ValueError("No active pipeline version found")
        
        config = PipelineConfig.parse_raw(version.config_json)
        
        # Execute pipeline (simplified - would integrate real retriever/generator)
        start_time = time.time()
        
        # Retrieval phase
        retrieval_start = time.time()
        chunks = await self._retrieve(config.retrieval, query)  # Implementation-specific
        retrieval_latency = int((time.time() - retrieval_start) * 1000)
        
        # Generation phase  
        generation_start = time.time()
        answer = await self._generate(config.generation, query, chunks)
        generation_latency = int((time.time() - generation_start) * 1000)
        
        total_latency = int((time.time() - start_time) * 1000)
        
        # Record run
        run = PipelineRun(
            pipeline_version_id=version.id,
            query=query,
            answer=answer,
            context_used=json.dumps(chunks),
            retrieval_latency_ms=retrieval_latency,
            generation_latency_ms=generation_latency,
            total_latency_ms=total_latency,
            input_tokens=1000,  # Would calculate from actual tokens
            output_tokens=len(answer.split()),
            cost_usd=0.02  # Would calculate from model pricing
        )
        self.db.add(run)
        await self.db.commit()
        
        return {
            "run_id": run.id,
            "answer": answer,
            "context": "\n\n".join(chunks),
            "chunks": chunks,
            "retrieval_latency_ms": retrieval_latency,
            "total_latency_ms": total_latency,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens
        }