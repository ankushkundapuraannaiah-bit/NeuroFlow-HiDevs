import asyncio
import json
import numpy as np
from scipy.stats import pearsonr
from evaluation.judge import EvaluationJudge
import evaluation.calibration.annotated_set as calibration_data

async def run_calibration_check():
    """Run calibration on 30 annotated examples."""
    judge = EvaluationJudge(None)  # No DB needed for calibration
    
    results = []
    for i, example in enumerate(calibration_data.ANNOTATED_EXAMPLES):
        print(f"Calibrating {i+1}/30...")
        
        metrics = await judge.evaluate(
            run_id=i,
            query=example["query"],
            answer=example["answer"],
            context=example["context"],
            chunks=example["chunks"]
        )
        results.append({
            "auto_score": metrics["overall_score"],
            "human_score": example["human_score"]
        })
    
    # Compute Pearson correlation
    auto_scores = [r["auto_score"] for r in results]
    human_scores = [r["human_score"] for r in results]
    
    correlation, _ = pearsonr(auto_scores, human_scores)
    
    calibration_results = {
        "correlation": float(correlation),
        "passes_threshold": correlation > 0.85,
        "n_examples": 30,
        "results": results
    }
    
    # Write results
    with open("evaluation/calibration_results.json", "w") as f:
        json.dump(calibration_results, f, indent=2)
    
    print(f"Calibration complete: {correlation:.3f} {'✅ PASS' if correlation > 0.85 else '❌ FAIL'}")
    return calibration_results

if __name__ == "__main__":
    asyncio.run(run_calibration_check())