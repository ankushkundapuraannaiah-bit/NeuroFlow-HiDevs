from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Dict, Any
import uuid
from backend.db.session import get_db
from backend.models.pipeline import PipelineConfig, PipelineVersion
from backend.db.models.pipeline import Pipeline, PipelineVersion as PipelineVersionModel, PipelineRun
from backend.services.pipeline_runner import PipelineRunner

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

@router.post("/", response_model=dict)
async def create_pipeline(
    config: PipelineConfig,
    db: AsyncSession = Depends(get_db)
):
    """Create new pipeline with validated config."""
    # Check if pipeline name exists
    existing = await db.execute(
        select(Pipeline).where(Pipeline.name == config.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Pipeline name already exists")
    
    # Create pipeline
    pipeline = Pipeline(
        name=config.name,
        description=config.description
    )
    db.add(pipeline)
    await db.flush()  # Get pipeline ID
    
    # Create version 1
    version = PipelineVersionModel(
        pipeline_id=pipeline.id,
        version=1,
        config_json=config.json()
    )
    db.add(version)
    
    # Update latest_version
    pipeline.latest_version = 1
    await db.commit()
    
    return {"pipeline_id": str(pipeline.id), "version": 1}

@router.get("/", response_model=List[Dict])
async def list_pipelines(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """List pipelines with latest metrics."""
    stmt = select(
        Pipeline,
        func.avg(PipelineRun.total_latency_ms).label("avg_latency"),
        func.avg(PipelineRun.cost_usd).label("avg_cost"),
        func.count(PipelineRun.id).label("run_count")
    ).outerjoin(
        PipelineRun,
        PipelineRun.pipeline_version_id == PipelineVersionModel.id
    ).group_by(Pipeline.id).limit(limit).offset(offset)
    
    result = await db.execute(stmt)
    pipelines = []
    
    for pipeline, avg_latency, avg_cost, run_count in result:
        pipelines.append({
            "id": str(pipeline.id),
            "name": pipeline.name,
            "description": pipeline.description,
            "run_count": run_count,
            "avg_latency_ms": int(avg_latency or 0),
            "avg_cost_usd": float(avg_cost or 0)
        })
    
    return pipelines

@router.patch("/{pipeline_id}", response_model=dict)
async def update_pipeline(
    pipeline_id: str,
    config: PipelineConfig,
    db: AsyncSession = Depends(get_db)
):
    """Update pipeline (creates new version)."""
    pipeline_uuid = uuid.UUID(pipeline_id)
    
    # Get current latest version
    stmt = select(
        Pipeline.latest_version,
        func.coalesce(func.max(PipelineVersionModel.version), 0).label("max_version")
    ).join(
        PipelineVersionModel,
        PipelineVersionModel.pipeline_id == Pipeline.id
    ).where(Pipeline.id == pipeline_uuid)
    
    result = await db.execute(stmt)
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Pipeline not found")
    
    new_version = (row.max_version or 0) + 1
    
    # Create new version
    version = PipelineVersionModel(
        pipeline_id=pipeline_uuid,
        version=new_version,
        config_json=config.json()
    )
    db.add(version)
    
    # Update pipeline latest_version
    pipeline = await db.get(Pipeline, pipeline_uuid)
    pipeline.latest_version = new_version
    await db.commit()
    
    return {"pipeline_id": pipeline_id, "version": new_version}

@router.get("/{pipeline_id}/runs")
async def get_pipeline_runs(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0
):
    """Get paginated runs for pipeline."""
    pipeline_uuid = uuid.UUID(pipeline_id)
    
    stmt = select(PipelineRun).join(
        PipelineVersionModel,
        PipelineRun.pipeline_version_id == PipelineVersionModel.id
    ).where(
        PipelineVersionModel.pipeline_id == pipeline_uuid
    ).order_by(PipelineRun.created_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(stmt)
    runs = []
    for run in result.scalars():
        runs.append({
            "run_id": str(run.id),
            "query": run.query,
            "status": run.status,
            "total_latency_ms": run.total_latency_ms,
            "cost_usd": float(run.cost_usd or 0),
            "created_at": run.created_at.isoformat()
        })
    
    return {"runs": runs}