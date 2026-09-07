"""Daily AI editorial brief synthesizer using the Google Gemini API."""

from datetime import datetime, timezone
import logging
import os
import re
from typing import Any, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

FALLBACK_NO_KEY = "_API key not provided. Brief could not be synthesized._"
FALLBACK_API_ERROR = "_Brief could not be synthesized due to an API error._"

SYSTEM_INSTRUCTION = """You are an analytical research assistant in automated reasoning and mathematical sciences.
Your job is to evaluate today's candidate pool of math and AI preprints against a rigorous mathematical impact rubric and produce an authoritative, high-density editorial brief.

### Mathematical Novelty & Verification Rubric (1–5 scale):
- 5 (Landmark Breakthrough): Conclusively resolves or materially advances a known open conjecture, constructs major novel mathematical objects (e.g. extremal graphs, counterexamples), or verifies significant open theorems in interactive theorem provers (Lean 4, Isabelle/HOL).
- 4 (Substantive Mathematical Contribution): Genuine theoretical advance, non-trivial formalization of modern mathematical theories, or breakthrough neuro-symbolic reasoning architectures with proven mathematical utility.
- 3 (Notable Methodology / Rigorous Tool): Useful domain-specific proof automation, premise selection technique, or empirical math education tool with verified pedagogical impact.
- 2 (Incremental Improvement): Minor variations on standard models, narrow benchmark tuning, or routine applications without new mathematical insight.
- 1 / Disqualified: Prompt engineering on standard LLMs, trivial re-verifications of high-school problems, or evaluations solely on unverified/elementary benchmarks like GSM8K or MATH without mathematical novelty or formal verification. Disqualify papers scoring 1.

### Output Template:
Format your response in GitHub-flavored Markdown following this exact structure:

# ☕ Daily Math-AI Brief — [Date]

[1–2 sentences synthesizing today's overarching trends, notable mathematical directions, and quality across the candidate pool.]

### 1. Mathematical Results via AI
[Curated analysis of qualifying papers under this pillar. Highlight the exact mathematical result, methodology, and significance. Cite paper titles as Markdown links to their URLs. If no candidates qualify or none exist, state: "No qualifying submissions met the threshold today."]

### 2. Theorem Proving & Reasoning Architectures
[Curated analysis of qualifying papers under this pillar. Highlight formal verification, autoformalization, or architectural advances. Cite paper titles as Markdown links to their URLs. If no candidates qualify or none exist, state: "No qualifying submissions met the threshold today."]

### 3. AI in Mathematics Education
[Curated analysis of qualifying papers under this pillar. Highlight pedagogical tools, step-by-step reasoning tutors, or educational deployments. Cite paper titles as Markdown links to their URLs. If no candidates qualify or none exist, state: "No qualifying submissions met the threshold today."]

Be concise, academically rigorous, and direct. Do not hallucinate papers not present in the candidate pool.
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


def synthesize_brief(aggregated_data: dict[str, Any]) -> str:
    """Synthesize a daily editorial brief using the Gemini API based on aggregated papers.

    Args:
        aggregated_data: Aggregated payload containing 'updated_at' and 'pillars'.

    Returns:
        Markdown string containing the synthesized editorial brief, or a fallback string on failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not api_key.strip():
        logger.warning("GEMINI_API_KEY not found in environment. Skipping AI brief synthesis.")
        return FALLBACK_NO_KEY

    # Determine date stamp
    updated_at = str(aggregated_data.get("updated_at", ""))
    if len(updated_at) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", updated_at[:10]):
        date_str = updated_at[:10]
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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
        f"Please evaluate today's ({date_str}) candidate pool of math-AI papers and generate the Daily Math-AI Brief.\n\n"
        f"{candidates_text}"
    )

    try:
        client = genai.Client(api_key=api_key.strip())
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.2,
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        if response and response.text:
            brief = response.text.strip()
            logger.info("Successfully synthesized daily brief via Gemini API (%d chars).", len(brief))
            return brief
        logger.warning("Gemini API returned an empty response.")
        return FALLBACK_API_ERROR
    except Exception as exc:
        logger.error("Failed to generate AI brief via Gemini API: %s", exc)
        return f"{FALLBACK_API_ERROR} ({exc})"
