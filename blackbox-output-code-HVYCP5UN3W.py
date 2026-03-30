from typing import List, Dict
from collections import defaultdict
from .retriever import RetrievalResult

def reciprocal_rank_fusion(
    result_lists: List[List[RetrievalResult]], 
    k: int = 60
) -> List[RetrievalResult]:
    """RRF: score = sum(1/(k + rank)) across all retrieval lists"""
    
    # Group results by chunk_id
    chunk_scores: Dict[str, float] = defaultdict(float)
    chunk_ranks: Dict[str, List[int]] = defaultdict(list)
    
    for rank_list, results in enumerate(result_lists, 1):
        for rank, result in enumerate(results, 1):
            chunk_id = result.chunk_id
            chunk_scores[chunk_id] += 1.0 / (k + rank)
            chunk_ranks[chunk_id].append(rank)
    
    # Sort by RRF score
    scored_chunks = [
        (chunk_id, score, min(ranks))  # Use best rank for tie-breaking
        for chunk_id, score in chunk_scores.items()
        for ranks in [chunk_ranks[chunk_id]]
    ]
    
    scored_chunks.sort(key=lambda x: (-x[1], x[2]))  # Highest score, then best rank
    
    # Preserve original result objects, just re-rank
    all_results = []
    seen = set()
    for chunk_id, rrf_score, best_rank in scored_chunks:
        # Find original result with most complete metadata
        for result_list in result_lists:
            for result in result_list:
                if result.chunk_id == chunk_id and result.chunk_id not in seen:
                    all_results.append(
                        RetrievalResult(
                            chunk_id=result.chunk_id,
                            content=result.content,
                            score=rrf_score,
                            metadata=result.metadata,
                            rank=len(all_results) + 1
                        )
                    )
                    seen.add(chunk_id)
                    break
    
    return all_results