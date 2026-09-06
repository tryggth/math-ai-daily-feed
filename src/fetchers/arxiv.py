"""arXiv API fetcher with retry logic and Atom XML parsing."""

import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional
import requests

from src.schema import Paper

logger = logging.getLogger(__name__)

ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}

PILLAR_QUERIES = {
    "results": 'cat:math.CO OR cat:math.NT OR cat:cs.AI AND (all:"Ramanujan Machine" OR all:"counterexample" OR all:"combinatorial search" OR all:"conjecture")',
    "architecture": 'cat:cs.LO OR cat:cs.AI AND (all:"theorem proving" OR all:"Lean 4" OR all:"autoformalization" OR all:"premise selection" OR all:"proof assistant")',
    "education": 'cat:cs.CY OR cat:cs.AI AND (all:"intelligent tutoring" OR all:"math education" OR all:"pedagogical" OR all:"step-by-step reasoning")',
}


def parse_arxiv_xml(xml_content: str, pillar: str) -> list[Paper]:
    """Parse arXiv Atom XML response into a list of Paper objects."""
    papers: list[Paper] = []
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        logger.error("Failed to parse arXiv XML: %s", exc)
        return papers

    for entry in root.findall("atom:entry", ATOM_NS):
        entry_id = (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip()
        title = entry.findtext("atom:title", default="", namespaces=ATOM_NS) or ""
        summary = entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or ""
        published = entry.findtext("atom:published", default="", namespaces=ATOM_NS) or ""

        # Extract authors
        authors: list[str] = []
        for author_elem in entry.findall("atom:author", ATOM_NS):
            name = author_elem.findtext("atom:name", default="", namespaces=ATOM_NS)
            if name and name.strip():
                authors.append(name.strip())

        # Extract direct paper/abstract URL
        url = ""
        for link in entry.findall("atom:link", ATOM_NS):
            rel = link.attrib.get("rel")
            content_type = link.attrib.get("type", "")
            if rel == "alternate" or (rel is None and content_type == "text/html"):
                url = link.attrib.get("href", "")
                break
        if not url:
            url = entry_id

        if entry_id and title:
            papers.append(
                Paper(
                    id=entry_id,
                    title=title,
                    url=url,
                    authors=authors,
                    published=published,
                    summary=summary,
                    source="arXiv",
                    pillar=pillar,
                )
            )

    return papers


def fetch_arxiv(
    pillar: str,
    max_results: int = 15,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    timeout: float = 15.0,
    session: Optional[requests.Session] = None,
) -> list[Paper]:
    """Fetch recent papers from arXiv for a given pillar with exponential backoff."""
    if pillar not in PILLAR_QUERIES:
        raise ValueError(
            f"Unknown pillar: '{pillar}'. Supported pillars: {list(PILLAR_QUERIES.keys())}"
        )

    query = PILLAR_QUERIES[pillar]
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    client = session or requests

    for attempt in range(1, max_retries + 1):
        try:
            response = client.get(
                ARXIV_ENDPOINT,
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            return parse_arxiv_xml(response.text, pillar=pillar)
        except (requests.RequestException, ET.ParseError) as exc:
            logger.warning(
                "arXiv fetch attempt %d/%d failed for pillar '%s': %s",
                attempt,
                max_retries,
                pillar,
                exc,
            )
            if attempt == max_retries:
                logger.error(
                    "All %d attempts failed for arXiv pillar '%s'. Returning empty list.",
                    max_retries,
                    pillar,
                )
                return []
            sleep_time = backoff_factor * (2 ** (attempt - 1))
            time.sleep(sleep_time)

    return []
