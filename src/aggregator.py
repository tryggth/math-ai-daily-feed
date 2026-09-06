"""Aggregator orchestrating arXiv and Hugging Face fetchers with deduplication."""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Callable, Optional

from src.fetchers.arxiv import fetch_arxiv
from src.fetchers.huggingface import fetch_huggingface
from src.schema import Paper

logger = logging.getLogger(__name__)


def normalize_title(title: str) -> str:
    """Normalize paper title by lowercasing, removing punctuation, and collapsing whitespace."""
    if not title:
        return ""
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(cleaned.split())


def normalize_url(url: str) -> str:
    """Normalize paper URL by enforcing HTTPS and stripping trailing slashes/versions."""
    if not url:
        return ""
    trimmed = url.strip().rstrip("/")
    if trimmed.startswith("http://"):
        trimmed = "https://" + trimmed[7:]
    # Strip arXiv version suffix if present: e.g., /abs/2501.12345v1 -> /abs/2501.12345
    trimmed = re.sub(r"(arxiv\.org/abs/\d+\.\d+)v\d+", r"\1", trimmed)
    return trimmed.lower()


class Aggregator:
    """Orchestrates multi-source paper retrieval and canonical deduplication."""

    def __init__(
        self,
        arxiv_fetcher: Callable[..., list[Paper]] = fetch_arxiv,
        hf_fetcher: Callable[..., list[Paper]] = fetch_huggingface,
    ) -> None:
        self.arxiv_fetcher = arxiv_fetcher
        self.hf_fetcher = hf_fetcher

    def run(
        self,
        arxiv_limit: int = 15,
        hf_limit: int = 30,
    ) -> dict[str, Any]:
        """Fetch from all sources, normalize, deduplicate, and group by pillar."""
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()

        pillars: dict[str, list[Paper]] = {
            "results": [],
            "architecture": [],
            "education": [],
        }

        # 1. Fetch arXiv papers for all three pillars
        for pillar_name in ["results", "architecture", "education"]:
            try:
                raw_papers = self.arxiv_fetcher(pillar=pillar_name, max_results=arxiv_limit)
                for item in raw_papers:
                    paper = item if isinstance(item, Paper) else Paper(**item)
                    norm_url = normalize_url(paper.url)
                    norm_title = normalize_title(paper.title)

                    if norm_url and norm_url in seen_urls:
                        continue
                    if norm_title and norm_title in seen_titles:
                        continue

                    if norm_url:
                        seen_urls.add(norm_url)
                    if norm_title:
                        seen_titles.add(norm_title)

                    target_pillar = paper.pillar if paper.pillar in pillars else pillar_name
                    pillars[target_pillar].append(paper)
            except Exception as exc:
                logger.error("Error during arXiv fetch for pillar '%s': %s", pillar_name, exc)

        # 2. Fetch Hugging Face daily papers
        try:
            raw_hf_papers = self.hf_fetcher(limit=hf_limit)
            for item in raw_hf_papers:
                paper = item if isinstance(item, Paper) else Paper(**item)
                norm_url = normalize_url(paper.url)
                norm_title = normalize_title(paper.title)

                if norm_url and norm_url in seen_urls:
                    continue
                if norm_title and norm_title in seen_titles:
                    continue

                if norm_url:
                    seen_urls.add(norm_url)
                if norm_title:
                    seen_titles.add(norm_title)

                target_pillar = paper.pillar if paper.pillar in pillars else "architecture"
                pillars[target_pillar].append(paper)
        except Exception as exc:
            logger.error("Error during Hugging Face fetch: %s", exc)

        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "updated_at": updated_at,
            "pillars": pillars,
        }


def run(arxiv_limit: int = 15, hf_limit: int = 30) -> dict[str, Any]:
    """Convenience module function executing Aggregator.run()."""
    return Aggregator().run(arxiv_limit=arxiv_limit, hf_limit=hf_limit)
