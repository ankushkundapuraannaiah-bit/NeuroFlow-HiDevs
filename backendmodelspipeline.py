from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from enum import Enum
import uuid
from datetime import datetime

class ChunkingStrategy(str, Enum):
    FIXED = "fixed"
    HIERARCHICAL = "hierarchical"
    SENTENCE = "sentence"

class RerankerType(str, Enum):
    CROSS_ENCODER = "cross-encoder"
    COHERE = "cohere"

class SystemPromptVariant(str, Enum):
    PRECISE = "precise"
    CONVERSATIONAL = "conversational"
    LEGAL = "legal"

class PipelineConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=10, max_length=500)
    
    ingestion: Dict[str, Any] = Field(...)
    retrieval: Dict[str, Any] = Field(...)
    generation: Dict[str, Any] = Field(...)
    evaluation: Dict[str, Any] = Field(...)
    
    # Validate required fields
    @validator('ingestion')
    def validate_ingestion(cls, v):
        required = ['chunking_strategy', 'chunk_size_tokens', 'chunk_overlap_tokens']
        missing = [k for k in required if k not in v]
        if missing:
            raise ValueError(f"Missing required ingestion fields: {missing}")
        if not isinstance(v['chunking_strategy'], str):
            raise ValueError("chunking_strategy must be string")
        return v
    
    @validator('retrieval')
    def validate_retrieval(cls, v):
        required = ['dense_k', 'sparse_k', 'top_k_after_rerank']
        missing = [k for k in required if k not in v]
        if missing:
            raise ValueError(f"Missing required retrieval fields: {missing}")
        return v
    
    @validator('generation')
    def validate_generation(cls, v):
        if 'model_routing' not in v:
            raise ValueError("generation.model_routing is required")
        return v

class PipelineVersion(BaseModel):
    id: uuid.UUID
    pipeline_id: uuid.UUID
    version: int
    config: PipelineConfig
    status: str = "active"  # active, archived
    created_at: datetime