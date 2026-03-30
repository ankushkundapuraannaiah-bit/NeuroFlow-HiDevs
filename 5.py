import re
from typing import List, Dict, Any
from dataclasses import dataclass
from uuid import UUID

@dataclass
class Citation:
    reference: str           # "Source 1"
    chunk_id: str            # UUID string
    document_name: str
    page_number: int | None
    content_preview: str     # first 100 chars
    valid: bool = True

class CitationParser:
    @staticmethod
    def parse_response(response: str, context_chunks: List[Dict[str, Any]]) -> List[Citation]:
        """Extract [Source N] citations and map to chunk metadata"""
        citations = []
        
        # Find all [Source N] patterns
        source_pattern = r'\$Source\s+(\d+)\$'
        matches = list(re.finditer(source_pattern, response))
        
        for match in matches:
            source_num = int(match.group(1))
            reference = f"Source {source_num}"
            
            # Map to context chunk (1-indexed)
            chunk_idx = source_num - 1
            if 0 <= chunk_idx < len(context_chunks):
                chunk = context_chunks[chunk_idx]
                citations.append(Citation(
                    reference=reference,
                    chunk_id=str(chunk["chunk_id"]),
                    document_name=chunk.get("document_name", "unknown"),
                    page_number=chunk.get("page_number"),
                    content_preview=chunk["content"][:100] + "..." if len(chunk["content"]) > 100 else chunk["content"],
                    valid=True
                ))
            else:
                # Hallucinated citation
                citations.append(Citation(
                    reference=reference,
                    chunk_id="",
                    document_name="INVALID",
                    page_number=None,
                    content_preview="Hallucinated citation - source not in context",
                    valid=False
                ))
        
        return citations
    
    @staticmethod
    def has_hallucinated_citations(citations: List[Citation]) -> bool:
        return any(not c.valid for c in citations)