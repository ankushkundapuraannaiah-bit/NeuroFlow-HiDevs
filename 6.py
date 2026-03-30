from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class GenerationPrompt:
    system: str
    user: str
    query_type: str

class PromptBuilder:
    def __init__(self):
        self.templates = {
            "factual": "Provide a direct, concise answer. If multiple sources agree, cite all of them.",
            "analytical": "Analyze and synthesize across the provided sources. Identify agreements and contradictions.",
            "comparative": "Organize your response as a structured comparison. Use a table if appropriate.",
            "procedural": "Provide numbered steps. Each step must be cited."
        }
    
    def build(self, query: str, context: str, query_type: str, metadata: Dict[str, Any]) -> GenerationPrompt:
        base_system = """You are a precise research assistant. Answer the user's question using ONLY the provided context.
        
<instructions>
1. If the context does not contain enough information to answer fully, say so explicitly: "I don't have enough information in the provided context to answer this fully."
2. For every factual claim, definition, statistic, or specific detail, include a citation in the format [Source N] immediately after the sentence.
3. Do not introduce information, statistics, or claims not present in the context.
4. Number your sources sequentially starting from 1.
5. Be concise but comprehensive.
</instructions>

<context>
{context}
</context>

{query_type_instruction}

Format your final answer directly without repeating the query."""

        system_prompt = base_system.format(
            context=context,
            query_type_instruction=self.templates.get(query_type, self.templates["factual"])
        )
        
        return GenerationPrompt(
            system=system_prompt,
            user=query,
            query_type=query_type
        )