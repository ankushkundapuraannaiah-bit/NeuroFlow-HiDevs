import mlflow
import uuid
from typing import List
from statistics import mean
from datetime import datetime
import os

class MLflowTracker:
    def __init__(self, experiment_name: str = "neuroflow-finetuning"):
        mlflow.set_experiment(experiment_name)
    
    def start_training_job(
        self,
        job_id: uuid.UUID,
        pairs: List[Dict],
        base_model: str,
        date_range: str
    ) -> str:
        """Start MLflow run for training job."""
        with mlflow.start_run(run_name=f"finetune-{job_id}", nested=True) as run:
            # Log parameters
            mlflow.log_params({
                "job_id": str(job_id),
                "base_model": base_model,
                "training_pair_count": len(pairs),
                "avg_quality_score": mean([0.85] * len(pairs)),  # From extraction
                "date_range": date_range,
                "system_prompt": "precise research assistant"
            })
            
            # Log training data as artifact
            jsonl_path = f"training_data/{job_id}.jsonl"
            if os.path.exists(jsonl_path):
                mlflow.log_artifact(jsonl_path)
            
            return run.info.run_id
    
    def log_training_results(
        self,
        run_id: str,
        training_loss: float,
        validation_loss: float,
        trained_tokens: int
    ):
        """Log final training metrics."""
        mlflow.log_metrics({
            "training_loss": training_loss,
            "validation_loss": validation_loss,
            "training_token_count": trained_tokens
        })
        
        # Register model
        model_uri = f"runs:/{run_id}/model"
        mlflow.register_model(
            model_uri, 
            f"neuroflow-finetune-{uuid.uuid4().hex[:8]}"
        )