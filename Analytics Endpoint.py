@router.get("/{pipeline_id}/analytics")
async def get_pipeline_analytics(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
    days: int = 30
):
    """Pipeline analytics with percentiles."""
    pipeline_uuid = uuid.UUID(pipeline_id)
    
    # Latency percentiles (p50, p95, p99)
    latency_stmt = select(
        func.percentile_cont(0.5).within_group(PipelineRun.total_latency_ms).label("p50"),
        func.percentile_cont(0.95).within_group(PipelineRun.total_latency_ms).label("p95"),
        func.percentile_cont(0.99).within_group(PipelineRun.total_latency_ms).label("p99"),
        func.avg(PipelineRun.total_latency_ms).label("avg"),
        func.count(PipelineRun.id).label("run_count")
    ).join(
        PipelineVersionModel,
        PipelineRun.pipeline_version_id == PipelineVersionModel.id
    ).where(
        and_(
            PipelineVersionModel.pipeline_id == pipeline_uuid,
            PipelineRun.created_at >= func.now() - timedelta(days=days)
        )
    )
    
    latency_result = await db.execute(latency_stmt)
    latency_stats = latency_result.fetchone()
    
    # Evaluation averages
    eval_stmt = select(
        func.avg(Evaluation.overall_score).label("avg_overall"),
        func.avg(Evaluation.faithfulness).label("avg_faithfulness"),
        func.avg(Evaluation.answer_relevance).label("avg_relevance")
    ).join(
        PipelineRun,
        Evaluation.run_id == PipelineRun.id
    ).join(
        PipelineVersionModel,
        PipelineRun.pipeline_version_id == PipelineVersionModel.id
    ).where(
        PipelineVersionModel.pipeline_id == pipeline_uuid
    )
    
    eval_result = await db.execute(eval_stmt)
    eval_stats = eval_result.fetchone()
    
    # Cost stats
    cost_stmt = select(
        func.avg(PipelineRun.cost_usd).label("avg_cost"),
        func.sum(PipelineRun.cost_usd).label("total_cost")
    ).join(
        PipelineVersionModel,
        PipelineRun.pipeline_version_id == PipelineVersionModel.id
    ).where(
        PipelineVersionModel.pipeline_id == pipeline_uuid
    )
    
    cost_result = await db.execute(cost_stmt)
    cost_stats = cost_result.fetchone()
    
    # Daily query volume
    daily_stmt = select(
        func.date_trunc('day', PipelineRun.created_at).label("day"),
        func.count(PipelineRun.id).label("count")
    ).join(
        PipelineVersionModel,
        PipelineRun.pipeline_version_id == PipelineVersionModel.id
    ).where(
        and_(
            PipelineVersionModel.pipeline_id == pipeline_uuid,
            PipelineRun.created_at >= func.now() - timedelta(days=days)
        )
    ).group_by("day").order_by("day")
    
    daily_result = await db.execute(daily_stmt)
    daily_queries = [
        {"day": row.day.isoformat(), "count": row.count}
        for row in daily_result
    ]
    
    return {
        "latency_ms": {
            "p50": int(latency_stats.p50 or 0),
            "p95": int(latency_stats.p95 or 0),
            "p99": int(latency_stats.p99 or 0),
            "avg": int(latency_stats.avg or 0),
            "run_count": latency_stats.run_count
        },
        "evaluation": {
            "avg_overall": float(eval_stats.avg_overall or 0),
            "avg_faithfulness": float(eval_stats.avg_faithfulness or 0),
            "avg_relevance": float(eval_stats.avg_relevance or 0)
        },
        "cost_usd": {
            "avg_per_query": float(cost_stats.avg_cost or 0),
            "total": float(cost_stats.total_cost or 0)
        },
        "daily_queries": daily_queries
    }