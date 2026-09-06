"""Hugging Face Daily Papers fetcher with keyword filtering and pillar categorization."""

import json
import logging
import re
from typing import Any, Optional
import requests

from src.schema import Paper

logger = logging.getLogger(__name__)

HF_ENDPOINT = "https://huggingface.co/api/daily_papers"

MATH_KEYWORDS = [
    "theorem",
    "formal verification",
    "proof",
    "math reasoning",
    "mathematical reasoning",
    "conjecture",
]

RESULTS_KEYWORDS = [
    "conjecture",
    "counterexample",
    "combinatorial search",
    "ramanujan",
    "discovery",
    "open problem",
]


def is_math_relevant(text: str) -> bool:
    """Check if the given text matches math AI keywords."""
    lowered = text.lower()
    for kw in MATH_KEYWORDS:
        if kw in lowered:
            return True
    if re.search(r"\b(lean|lean4)\b", lowered):
        return True
    return False


def determine_pillar(text: str) -> str:
    """Determine pillar assignment ('results' or 'architecture') based on text content."""
    lowered = text.lower()
    for kw in RESULTS_KEYWORDS:
        if kw in lowered:
            return "results"
    return "architecture"


def parse_hf_paper(item: dict[str, Any]) -> Optional[Paper]:
    """Extract and validate a Paper object from a Hugging Face API paper item."""
    paper_data = item.get("paper") if isinstance(item.get("paper"), dict) else item

    paper_id = str(paper_data.get("id") or item.get("id") or "").strip()
    title = str(paper_data.get("title") or item.get("title") or "").strip()
    summary = str(paper_data.get("summary") or item.get("summary") or "").strip()
    published_raw = str(paper_data.get("publishedAt") or item.get("publishedAt") or "").strip()

    if not title:
        return None

    combined_text = f"{title} {summary}"
    if not is_math_relevant(combined_text):
        return None

    # Parse authors
    raw_authors = paper_data.get("authors") or item.get("authors") or []
    authors: list[str] = []
    for author in raw_authors:
        if isinstance(author, dict):
            name = author.get("name", "").strip()
            if name:
                authors.append(name)
        elif isinstance(author, str) and author.strip():
            authors.append(author.strip())

    pillar = determine_pillar(combined_text)
    url = f"https://huggingface.co/papers/{paper_id}" if paper_id else ""
    canonical_id = f"hf:{paper_id}" if paper_id else url

    return Paper(
        id=canonical_id,
        title=title,
        url=url,
        authors=authors,
        published=published_raw,
        summary=summary,
        source="Hugging Face",
        pillar=pillar,
    )


def fetch_huggingface(
    limit: int = 30,
    timeout: float = 10.0,
    session: Optional[requests.Session] = None,
) -> list[Paper]:
    """Fetch and filter daily papers from Hugging Face API."""
    client = session or requests
    try:
        response = client.get(
            HF_ENDPOINT,
            params={"limit": limit},
            timeout=timeout,
        )
        if response.status_code in (429, 500, 502, 503, 504):
            logger.warning("Hugging Face API returned status %d", response.status_code)
            return []
        response.raise_for_status()
        items = response.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        logger.warning("Failed to fetch Hugging Face daily papers: %s", exc)
        return []

    papers: list[Paper] = []
    if not isinstance(items, list):
        return papers

    for item in items[:limit]:
        if isinstance(item, dict):
            paper = parse_hf_paper(item)
            if paper is not None:
                papers.append(paper)

    return papers
