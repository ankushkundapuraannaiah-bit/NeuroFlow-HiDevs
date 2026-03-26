# ADR 003 — Evaluation Framework

**Status:** Accepted  
**Date:** 2026-03-26  
**Deciders:** Platform Team

---

## Context

Every RAG generation in NeuroFlow must be evaluated for quality across four dimensions: faithfulness, answer relevance, context precision, and context recall. We need to score every generation — not a sample — to detect regressions quickly, build a high-quality training dataset for fine-tuning, and surface quality trends per pipeline and model.

Two evaluation paradigms are available:

**Human annotation** produces high-quality, nuanced scores. Annotators can catch subtle hallucinations, judge tone and completeness, and identify factual errors that require external knowledge. The problems are volume and latency. NeuroFlow targets hundreds to thousands of queries per day per pipeline. Hiring and maintaining an annotation team to score every generation is cost-prohibitive. Even with crowd-sourcing, annotation turnaround is hours to days, which is too slow for real-time quality monitoring and fine-tuning dataset construction.

**LLM-as-judge (automated evaluation)** uses a capable LLM (GPT-4o) as a scoring proxy. The judge receives the query, the retrieved context, and the generated answer, and is prompted to assess each metric using a detailed rubric. Automated evaluation is fast (~2–3 seconds per generation), cheap (~$0.002 per evaluation at GPT-4o-mini), scales horizontally with query volume, and produces structured numeric scores that can feed directly into SQL aggregates and fine-tuning selection criteria.

We also evaluated **RAGAS**, an open-source framework that implements similar LLM-as-judge metrics with standardized prompts. RAGAS would give us a reproducible baseline but limits our ability to customize metric definitions to NeuroFlow's specific use cases (e.g., our faithfulness rubric considers citation accuracy, not just factual grounding).

---

## Decision

We will use **automated LLM-as-judge evaluation as the primary scoring mechanism**, supplemented by voluntary user star ratings (1–5) as a weak human signal.

The evaluation stack is:

- **Scorer LLM:** GPT-4o (full) for faithfulness and context recall (most nuanced), GPT-4o-mini for answer relevance and context precision (simpler classification tasks).
- **Metric implementation:** Custom prompts per metric, structured JSON output enforced via function calling.
- **Human signal:** Users can optionally rate responses 1–5. Ratings are stored alongside automated scores and used in fine-tuning selection (`faithfulness > 0.8 AND user_rating >= 4`).
- **Spot-check human annotation:** A stratified random sample of 50 generations per week is sent to human annotators to calibrate automated scores. If the Pearson correlation between automated faithfulness and human faithfulness drops below 0.7, we treat it as a scoring drift alert.

Human annotation is not abandoned — it is used for calibration and for auditing edge cases where automated scores disagree with user ratings.

---

## Consequences

**Positive:**

- Scores every generation within seconds of completion — enables real-time dashboards and fast regression detection.
- Cost scales predictably at ~$0.002 per generation vs. ~$0.50–$2.00 for human annotation.
- Structured numeric output integrates directly with Postgres aggregates, Prometheus metrics, and fine-tuning selection SQL.
- Custom prompts allow NeuroFlow-specific rubrics (e.g., citation accuracy, domain-appropriate tone).
- Enables a continuous fine-tuning flywheel: automated scoring → high-quality example selection → fine-tuning → better generation → better scores.

**Failure Modes and Detection:**

**1. Position bias.** LLM judges prefer content that appears first in the context window, inflating faithfulness scores for generations that echo the top-ranked chunk even when the answer is factually incomplete. Detection: we will periodically shuffle chunk order in evaluation prompts and measure score variance. A variance above 0.05 triggers a prompt redesign.

**2. Sycophancy / verbosity bias.** The judge LLM may score longer, more confident-sounding answers higher regardless of accuracy. Detection: weekly human calibration set with deliberately verbose but incorrect generations; alert if automated faithfulness > 0.7 for human-labeled hallucinations.

**3. Metric gaming.** If models are fine-tuned on data selected by automated scores, they may learn to produce outputs that score well on the judge's rubric without being genuinely useful. Detection: monitor user star ratings independently of automated scores. Divergence between rolling automated score and rolling user rating triggers a human audit.

**4. Judge model updates.** OpenAI updates GPT-4o periodically. A silent model update could shift the scoring distribution, making historical comparisons invalid. Mitigation: pin the judge to a specific model snapshot (`gpt-4o-2024-11-20`). Run regression tests on a frozen 500-query gold set before accepting a new snapshot.

**5. Cost runaway.** At high query volume, evaluation costs can spike. Mitigation: async evaluation workers run at low priority, capped at 500 evaluations per minute. Overflow evaluations are queued and processed within 15 minutes. Critical-path query latency is never affected.

**Conditions for Increasing Human Annotation:**

If any of the following are observed over a 7-day window, we will increase human annotation sampling from 50 to 500 per week: automated-vs-human Pearson correlation drops below 0.7; user star ratings trend down while automated scores trend up; a model promotion event is pending (human verification required before promotion).
