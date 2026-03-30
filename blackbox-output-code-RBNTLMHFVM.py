import asyncio
import json
from pipelines.retrieval.retrieval_pipeline import RetrievalPipeline

TEST_SET = [
    {
        "query": "What is HNSW indexing?",
        "relevant_chunk_ids": ["chunk_hnsw_001", "chunk_hnsw_002"]
    },
    {
        "query": "How does attention work in transformers?",
        "relevant_chunk_ids": ["chunk_attention_001", "chunk_transformer_001"]
    },
    {
        "query": "Show me 2023 documents about climate change",
        "relevant_chunk_ids": ["chunk_climate_2023_001"]
    },
    # Add 17 more test cases...
] * 7  # Make 20 total

async def evaluate_retrieval(pipeline: RetrievalPipeline):
    hit_rate = 0
    mrr = 0
    
    for test in TEST_SET:
        results = await pipeline.retrieve(test["query"], k=10)
        
        # Hit Rate: any relevant chunk in top-k?
        hit = any(r.chunk_id in test["relevant_chunk_ids"] for r in results[2])
        if hit:
            hit_rate += 1
            
            # MRR: reciprocal of first relevant rank
            for i, r in enumerate(results[2]):
                if r.chunk_id in test["relevant_chunk_ids"]:
                    mrr += 1 / (i + 1)
                    break
    
    hit_rate /= len(TEST_SET)
    mrr /= len(TEST_SET)
    
    results = {
        "hit_rate": hit_rate,
        "mrr": mrr,
        "meets_thresholds": hit_rate > 0.75 and mrr > 0.55,
        "test_set_size": len(TEST_SET)
    }
    
    print(f"Hit Rate: {hit_rate:.3f} | MRR: {mrr:.3f} | PASS: {results['meets_thresholds']}")
    
    with open("evaluation/retrieval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    return results

# Run evaluation
async def main():
    pipeline = RetrievalPipeline(
        db_connection_string="your_db_connection",
        openai_api_key="your_openai_key"
    )
    await evaluate_retrieval(pipeline)

if __name__ == "__main__":
    asyncio.run(main())