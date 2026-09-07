"""Aggregator orchestrating arXiv and Hugging Face fetchers with historical deduplication and freshness filtering."""

from datetime import date, datetime, timezone
import json
import logging
import os
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


def extract_arxiv_id(identifier: str) -> str:
    """Extract canonical arXiv ID without version suffix (e.g. '2609.04170' from '2609.04170v2' or URLs)."""
    if not identifier:
        return ""
    match = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", identifier)
    if match:
        return match.group(1)
    return ""


def is_fresh(
    published_date_str: str,
    max_age_days: int = 5,
    reference_date: Optional[date] = None,
) -> bool:
    """Validate that published_date_str (YYYY-MM-DD) is within max_age_days of reference_date."""
    if not published_date_str:
        return False
    try:
        clean_date_str = str(published_date_str)[:10]
        pub_date = datetime.strptime(clean_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False

    ref = reference_date or datetime.now(timezone.utc).date()
    age = (ref - pub_date).days
    return -1 <= age <= max_age_days


def _add_identifiers(
    item_url: str,
    item_title: str,
    item_id: str,
    seen_set: set[str],
) -> None:
    """Helper to populate canonical keys into seen_set."""
    if item_url:
        norm_u = normalize_url(item_url)
        if norm_u:
            seen_set.add(norm_u)

    if item_title:
        norm_t = normalize_title(item_title)
        if norm_t:
            seen_set.add(norm_t)

    if item_id:
        seen_set.add(str(item_id).strip().lower())

    aid = extract_arxiv_id(item_id) or extract_arxiv_id(item_url)
    if aid:
        seen_set.add(f"arxiv:{aid}")


def is_paper_seen(paper: Paper, seen_identifiers: set[str]) -> bool:
    """Check whether a paper has already been encountered in seen_identifiers."""
    norm_u = normalize_url(paper.url)
    if norm_u and norm_u in seen_identifiers:
        return True

    norm_t = normalize_title(paper.title)
    if norm_t and norm_t in seen_identifiers:
        return True

    norm_id = paper.id.strip().lower()
    if norm_id and norm_id in seen_identifiers:
        return True

    aid = extract_arxiv_id(paper.id) or extract_arxiv_id(paper.url)
    if aid and f"arxiv:{aid}" in seen_identifiers:
        return True

    return False


def add_paper_to_seen(paper: Paper, seen_identifiers: set[str]) -> None:
    """Register a paper's identifiers in seen_identifiers."""
    _add_identifiers(paper.url, paper.title, paper.id, seen_identifiers)


def load_historical_seen_identifiers(
    data_dir: str = "data",
    exclude_date: Optional[str] = None,
) -> set[str]:
    """Scan data_dir for all historical *.json files and collect normalized identifiers.

    Args:
        data_dir: Directory containing historical JSON snapshot files.
        exclude_date: Optional YYYY-MM-DD date string to skip (e.g. today's date when re-running).

    Returns:
        Consolidated set of seen URLs, titles, IDs, and arXiv numbers.
    """
    seen: set[str] = set()
    if not data_dir or not os.path.isdir(data_dir):
        return seen

    try:
        filenames = os.listdir(data_dir)
    except OSError as exc:
        logger.warning("Could not read directory %s: %s", data_dir, exc)
        return seen

    exclude_filename = f"{exclude_date}.json" if exclude_date else None

    for fname in filenames:
        if not fname.endswith(".json") or fname == exclude_filename:
            continue
        filepath = os.path.join(data_dir, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = json.load(f)
            pillars = content.get("pillars", {})
            if not isinstance(pillars, dict):
                continue
            for pillar_papers in pillars.values():
                if not isinstance(pillar_papers, list):
                    continue
                for p in pillar_papers:
                    if isinstance(p, dict):
                        _add_identifiers(
                            p.get("url", ""),
                            p.get("title", ""),
                            p.get("id", ""),
                            seen,
                        )
                    elif hasattr(p, "to_dict"):
                        pd = p.to_dict()
                        _add_identifiers(
                            pd.get("url", ""),
                            pd.get("title", ""),
                            pd.get("id", ""),
                            seen,
                        )
        except Exception as exc:
            logger.warning("Error reading historical snapshot %s: %s", filepath, exc)

    logger.info("Loaded %d historical identifiers from %s", len(seen), data_dir)
    return seen


class Aggregator:
    """Orchestrates multi-source paper retrieval, historical deduplication, and freshness filtering."""

    def __init__(
        self,
        arxiv_fetcher: Callable[..., list[Paper]] = fetch_arxiv,
        hf_fetcher: Callable[..., list[Paper]] = fetch_huggingface,
        data_dir: str = "data",
    ) -> None:
        self.arxiv_fetcher = arxiv_fetcher
        self.hf_fetcher = hf_fetcher
        self.data_dir = data_dir

    def run(
        self,
        arxiv_limit: int = 15,
        hf_limit: int = 30,
        data_dir: Optional[str] = None,
        max_age_days: int = 5,
        reference_date: Optional[date] = None,
        current_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fetch from all sources, filter by freshness, deduplicate across history and categories."""
        active_data_dir = data_dir if data_dir is not None else self.data_dir
        today_str = current_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Load historical seen identifiers (excluding today's date if re-running)
        seen_identifiers = load_historical_seen_identifiers(
            data_dir=active_data_dir,
            exclude_date=today_str,
        )

        pillars: dict[str, list[Paper]] = {
            "results": [],
            "architecture": [],
            "education": [],
        }

        def process_candidate(item: Any, default_pillar: str) -> bool:
            paper = item if isinstance(item, Paper) else Paper(**item)

            # 1. Freshness check: reject papers older than max_age_days
            if not is_fresh(paper.published, max_age_days=max_age_days, reference_date=reference_date):
                logger.debug("Discarding stale paper (%s): %s", paper.published, paper.title)
                return False

            # 2. Historical & intra-day deduplication check
            if is_paper_seen(paper, seen_identifiers):
                logger.debug("Discarding previously seen paper: %s", paper.title)
                return False

            # 3. Novel candidate: register in seen_identifiers and add to target pillar
            add_paper_to_seen(paper, seen_identifiers)
            target_pillar = paper.pillar if paper.pillar in pillars else default_pillar
            pillars[target_pillar].append(paper)
            return True

        # 1. Fetch arXiv papers for all three pillars
        for pillar_name in ["results", "architecture", "education"]:
            try:
                raw_papers = self.arxiv_fetcher(pillar=pillar_name, max_results=arxiv_limit)
                for item in raw_papers:
                    process_candidate(item, default_pillar=pillar_name)
            except Exception as exc:
                logger.error("Error during arXiv fetch for pillar '%s': %s", pillar_name, exc)

        # 2. Fetch Hugging Face daily papers
        try:
            raw_hf_papers = self.hf_fetcher(limit=hf_limit)
            for item in raw_hf_papers:
                process_candidate(item, default_pillar="architecture")
        except Exception as exc:
            logger.error("Error during Hugging Face fetch: %s", exc)

        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "updated_at": updated_at,
            "pillars": pillars,
        }


def run(
    arxiv_limit: int = 15,
    hf_limit: int = 30,
    data_dir: str = "data",
    max_age_days: int = 5,
    reference_date: Optional[date] = None,
    current_date: Optional[str] = None,
) -> dict[str, Any]:
    """Convenience module function executing Aggregator.run()."""
    return Aggregator(data_dir=data_dir).run(
        arxiv_limit=arxiv_limit,
        hf_limit=hf_limit,
        data_dir=data_dir,
        max_age_days=max_age_days,
        reference_date=reference_date,
        current_date=current_date,
    )
