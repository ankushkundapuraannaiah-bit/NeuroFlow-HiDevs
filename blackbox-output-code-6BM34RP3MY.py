import asyncio
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import openai
import re

@dataclass
class ProcessedQuery:
    original: str
    expansions: List[str]
    metadata_filters: Dict[str, str]
    query_type: str  # factual, analytical, comparative, procedural

class QueryProcessor:
    def __init__(self, openai_api_key: str):
        openai.api_key = openai_api_key
    
    async def process(self, raw_query: str) -> ProcessedQuery:
        # Run all processing in parallel
        expansions, filters, qtype = await asyncio.gather(
            self._generate_expansions(raw_query),
            self._extract_metadata_filters(raw_query),
            self._classify_query_type(raw_query)
        )
        
        return ProcessedQuery(
            original=raw_query,
            expansions=expansions,
            metadata_filters=filters,
            query_type=qtype
        )
    
    async def _generate_expansions(self, query: str) -> List[str]:
        prompt = f"""
        Generate 2-3 alternative phrasings of this query that would retrieve the same relevant information.
        Original: "{query}"
        Return only the alternative queries, one per line, no numbering or explanation.
        """
        
        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3
            )
            expansions = response.choices[0].message.content.strip().split('\n')
            return [e.strip() for e in expansions if e.strip()][:3]
        except:
            # Fallback: simple expansions
            return [query, query.replace("how does", "explain"), query.replace("what is", "describe")]
    
    async def _extract_metadata_filters(self, query: str) -> Dict[str, str]:
        # Regex patterns for common metadata filters
        patterns = {
            'year': r'(?:from|in)\s+(\d{4})',
            'topic': r'(?:about|on)\s+([a-zA-Z\s]+?)(?:\s+(?:from|in|about)|$)',
            'author': r'by\s+([a-zA-Z\s]+?)(?:\s+(?:from|in)|$)'
        }
        
        filters = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, query.lower())
            if match:
                filters[key] = match.group(1).strip()
        
        return filters
    
    async def _classify_query_type(self, query: str) -> str:
        keywords = {
            'factual': ['what is', 'define', 'explain'],
            'analytical': ['why', 'how does', 'compare', 'analyze'],
            'comparative': ['vs', 'versus', 'compare', 'difference'],
            'procedural': ['how to', 'steps', 'process', 'tutorial']
        }
        
        query_lower = query.lower()
        for qtype, terms in keywords.items():
            if any(term in query_lower for term in terms):
                return qtype
        
        return 'factual'  # default