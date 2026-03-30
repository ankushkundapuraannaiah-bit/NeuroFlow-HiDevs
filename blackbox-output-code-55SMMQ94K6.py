import tiktoken
from typing import List, Dict, Any, Tuple

class ContextAssembler:
    def __init__(self, token_budget: int = 4000):
        self.token_budget = token_budget
        self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def assemble(self, results: List[RetrievalResult], k: int = 10) -> Tuple[str, Dict[str, Any]]:
        """Assemble top-k chunks into formatted context within token budget"""
        
        context_parts = []
        total_tokens = 0
        chunks_used = []
        sources = set()
        
        for result in results[:k]:
            # Format chunk with source info
            source_info = f"[Source — {result.metadata.get('document_name', 'unknown')}, page {result.metadata.get('page', 'N/A')}]"
            chunk_text = f"{source_info}\n{result.content}\n"
            
            chunk_tokens = len(self.encoding.encode(chunk_text))
            
            if total_tokens + chunk_tokens > self.token_budget:
                break
            
            context_parts.append(chunk_text)
            total_tokens += chunk_tokens
            chunks_used.append({
                "chunk_id": result.chunk_id,
                "tokens": chunk_tokens,
                "score": result.score
            })
            sources.add(f"{result.metadata.get('document_name', 'unknown')} (page {result.metadata.get('page', 'N/A')})")
        
        context = "\n\n".join(context_parts)
        
        return context, {
            "chunks_used": chunks_used,
            "total_tokens": total_tokens,
            "sources": list(sources),
            "num_chunks": len(chunks_used)
        }