from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from .base import Base

class FinetuneJob(Base):
    __tablename__ = "finetune_jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_job_id = Column(String(100), unique=True, index=True)
    base_model = Column(String(100))
    fine_tuned_model = Column(String(100))
    status = Column(String(20), default="queued")  # queued, running, succeeded, failed
    mlflow_run_id = Column(String(100))
    training_file_id = Column(String(100))
    pair_count = Column(Integer)
    training_loss_final = Column(Float)
    validation_loss_final = Column(Float)
    trained_tokens = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))