"""Daily AI editorial brief synthesizer using the Google Gemini API."""

from datetime import datetime, timezone
import logging
import os
import re
from typing import Any, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

FALLBACK_NO_KEY = "_API key not provided. Brief could not be synthesized._"
FALLBACK_API_ERROR = "_Brief could not be synthesized due to an API error._"

SYSTEM_INSTRUCTION_TEMPLATE = """You are an analytical research assistant in automated reasoning and mathematical sciences.
Your job is to evaluate today's candidate pool of math and AI preprints against a rigorous mathematical impact rubric and produce an authoritative, high-density editorial brief.

### Mathematical Novelty & Verification Rubric (1–5 scale):
- 5 (Landmark Breakthrough): Conclusively resolves or materially advances a known open conjecture, constructs major novel mathematical objects (e.g. extremal graphs, counterexamples), or verifies significant open theorems in interactive theorem provers (Lean 4, Isabelle/HOL).
- 4 (Substantive Mathematical Contribution): Genuine theoretical advance, non-trivial formalization of modern mathematical theories, or breakthrough neuro-symbolic reasoning architectures with proven mathematical utility.
- 3 (Notable Methodology / Rigorous Tool): Useful domain-specific proof automation, premise selection technique, or empirical math education tool with verified pedagogical impact.
- 2 (Incremental Improvement): Minor variations on standard models, narrow benchmark tuning, or routine applications without new mathematical insight.
- 1 / Disqualified: Prompt engineering on standard LLMs, trivial re-verifications of high-school problems, or evaluations solely on unverified/elementary benchmarks like GSM8K or MATH without mathematical novelty or formal verification. Disqualify papers scoring 1.

### Mandatory Entry Schema:
For each summarized paper in any pillar, you MUST include:
* **[Title / Key Result]**
  [Paper Title Linked to URL](url) — Authors
  - **Mathematical Impact:** (Score: 1–5 — Label). [Concise explanation of mathematical advance]
  - **AI Connection:** [Describe the exact role AI/computation played. STRICT GROUNDING RULE: State only what is explicitly described in the provided abstract. Specify the concrete mechanism (e.g., MCTS tactic search, GNN for graph invariants, SAT-solver certificate, LLM hint generation). If the paper uses classical combinatorial algorithms or symbolic solvers without neural networks, state: "Classical symbolic computation / constraint solver (no neural AI)". If the abstract claims AI assistance without detailing the architecture, state: "Unspecified AI assistance claimed in abstract; architecture not detailed." Never invent or infer unmentioned models, architectures, or training regimens.]

### Output Template:
Format your response in GitHub-flavored Markdown following this exact structure:

# ☕ Daily Math-AI Brief — [Date]

[1–2 sentences synthesizing today's overarching trends, notable mathematical directions, and quality across the candidate pool.]

### 1. Mathematical Results via AI
[Curated analysis of qualifying papers under this pillar using the mandatory entry schema. If no candidates qualify or none exist, state: "No qualifying submissions met the threshold today."]

### 2. Theorem Proving & Reasoning Architectures
[Curated analysis of qualifying papers under this pillar using the mandatory entry schema. If no candidates qualify or none exist, state: "No qualifying submissions met the threshold today."]

### 3. AI in Mathematics Education
[Curated analysis of qualifying papers under this pillar using the mandatory entry schema. If no candidates qualify or none exist, state: "No qualifying submissions met the threshold today."]

### Provenance Footer:
At the very end of the markdown text, you MUST append:
---
*Synthesized with `{model_name}` on {utc_timestamp}*

Be concise, academically rigorous, and direct. Do not hallucinate papers or unmentioned AI techniques not present in the candidate pool.
"""


def _get_field(item: Any, key: str, default: Any = "") -> Any:
    """Retrieve attribute or dict key seamlessly."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _format_candidates_for_pillar(papers: list[Any]) -> str:
    """Format candidate papers under a pillar for the prompt."""
    if not papers:
        return "No candidate papers submitted for this pillar today."

    lines = []
    for idx, paper in enumerate(papers, 1):
        title = _get_field(paper, "title", "Untitled")
        url = _get_field(paper, "url", "")
        raw_authors = _get_field(paper, "authors", [])
        authors = ", ".join(raw_authors) if isinstance(raw_authors, (list, tuple)) else str(raw_authors)
        summary = _get_field(paper, "summary", "").strip()
        source = _get_field(paper, "source", "Unknown")

        lines.append(
            f"Paper {idx}:\n"
            f"- Title: {title}\n"
            f"- Authors: {authors}\n"
            f"- URL: {url}\n"
            f"- Source: {source}\n"
            f"- Summary: {summary}\n"
        )
    return "\n".join(lines)


def synthesize_brief(aggregated_data: dict[str, Any]) -> tuple[str, str]:
    """Synthesize a daily editorial brief using the Gemini API based on aggregated papers.

    Args:
        aggregated_data: Aggregated payload containing 'updated_at' and 'pillars'.

    Returns:
        tuple[str, str]: (brief_markdown, model_used)
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        logger.warning("GEMINI_API_KEY not found in environment. Skipping AI brief synthesis.")
        return (FALLBACK_NO_KEY, "none")

    # Determine date stamp
    updated_at = str(aggregated_data.get("updated_at", ""))
    if len(updated_at) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", updated_at[:10]):
        date_str = updated_at[:10]
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    pillars = aggregated_data.get("pillars", {})
    if not isinstance(pillars, dict):
        pillars = {}

    results_papers = pillars.get("results", [])
    arch_papers = pillars.get("architecture", [])
    edu_papers = pillars.get("education", [])

    candidates_text = (
        f"Date: {date_str}\n\n"
        f"=== PILLAR 1: MATHEMATICAL RESULTS VIA AI ===\n"
        f"{_format_candidates_for_pillar(results_papers)}\n\n"
        f"=== PILLAR 2: THEOREM PROVING & REASONING ARCHITECTURES ===\n"
        f"{_format_candidates_for_pillar(arch_papers)}\n\n"
        f"=== PILLAR 3: AI IN MATHEMATICS EDUCATION ===\n"
        f"{_format_candidates_for_pillar(edu_papers)}\n"
    )

    prompt = (
        f"Please evaluate today's ({date_str}) candidate pool of math-AI papers and generate the Daily Math-AI Brief.\n"
        f"Enforce the strict grounding rule for the '**AI Connection:**' field on every summarized paper.\n\n"
        f"{candidates_text}"
    )

    try:
        client = genai.Client(api_key=api_key.strip())

        # Build candidate list starting with configured MODEL_NAME
        models_to_try = [MODEL_NAME]
        for fallback in ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-2.5-flash"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_exc: Optional[Exception] = None
        for model_cand in models_to_try:
            try:
                system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.replace(
                    "{model_name}", model_cand
                ).replace("{utc_timestamp}", now_utc)

                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                )

                response = client.models.generate_content(
                    model=model_cand,
                    contents=prompt,
                    config=config,
                )
                if response and response.text:
                    brief = response.text.strip()
                    model_used = model_cand

                    # Ensure provenance footer is present
                    provenance_pattern = f"*Synthesized with `{model_used}`"
                    if provenance_pattern not in brief:
                        brief += f"\n\n---\n*Synthesized with `{model_used}` on {now_utc}*"

                    logger.info(
                        "Successfully synthesized daily brief via %s (%d chars).",
                        model_used,
                        len(brief),
                    )
                    return (brief, model_used)
            except Exception as model_err:
                last_exc = model_err
                logger.warning("Model %s failed: %s. Attempting fallback model...", model_cand, model_err)
                continue

        if last_exc:
            raise last_exc

        logger.warning("Gemini API returned an empty response.")
        return (FALLBACK_API_ERROR, "none")
    except Exception as exc:
        logger.error("Failed to generate AI brief via Gemini API: %s", exc)
        return (f"{FALLBACK_API_ERROR} ({exc})", "none")
