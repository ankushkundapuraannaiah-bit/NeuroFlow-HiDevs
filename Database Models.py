from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid
from backend.models.pipeline import PipelineConfig
import json

Base = declarative_base()

class Pipeline(Base):
    __tablename__ = "pipelines"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500), nullable=False)
    status = Column(String(20), default="active")  # active, archived
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    latest_version = Column(Integer)

class PipelineVersion(Base):
    __tablename__ = "pipeline_versions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("pipelines.id"), nullable=False)
    version = Column(Integer, nullable=False)
    config_json = Column(Text, nullable=False)
    status = Column(String(20), default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_version_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_versions.id"), nullable=False)
    query = Column(Text, nullable=False)
    answer = Column(Text)
    context_used = Column(Text)  # JSON chunks
    retrieval_latency_ms = Column(Integer)
    generation_latency_ms = Column(Integer)
    total_latency_ms = Column(Integer)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    cost_usd = Column(Float)
    status = Column(String(20), default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())