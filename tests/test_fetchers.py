"""Tests for arXiv, Hugging Face fetchers, schema, and aggregator."""

import json
from unittest.mock import MagicMock, patch
import pytest
import requests

from src import aggregator
from src.fetchers.arxiv import fetch_arxiv, parse_arxiv_xml
from src.fetchers.huggingface import (
    determine_pillar,
    fetch_huggingface,
    is_math_relevant,
    parse_hf_paper,
)
from src.schema import Paper

MOCK_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <entry>
    <id>http://arxiv.org/abs/2609.00001v1</id>
    <title>
      Automated Conjecture Generation
      with Ramanujan Machines
    </title>
    <summary>
      We present a combinatorial search system for finding counterexamples
      to open mathematical conjectures.
    </summary>
    <published>2026-09-01T12:00:00Z</published>
    <author>
      <name>Alice Lovelace</name>
    </author>
    <author>
      <name>Bob Turing</name>
    </author>
    <link rel="alternate" type="text/html" href="https://arxiv.org/abs/2609.00001v1"/>
    <link rel="related" type="application/pdf" href="https://arxiv.org/pdf/2609.00001v1"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2609.00002v1</id>
    <title>Lean 4 Autoformalization Benchmark</title>
    <summary>Step-by-step reasoning in interactive theorem provers.</summary>
    <published>2026-09-02T15:30:00Z</published>
    <author>
      <name>Carol Ramanujan</name>
    </author>
    <link rel="alternate" type="text/html" href="https://arxiv.org/abs/2609.00002v1"/>
  </entry>
</feed>
"""

MOCK_HF_JSON = [
    {
        "paper": {
            "id": "2609.01111",
            "title": "AlphaProof: Neural Theorem Proving in Lean 4",
            "summary": "We introduce a formal verification pipeline for automated mathematical reasoning.",
            "publishedAt": "2026-09-03T10:00:00.000Z",
            "authors": [{"name": "David Hilbert"}, {"name": "Emmy Noether"}],
        }
    },
    {
        "paper": {
            "id": "2609.02222",
            "title": "Disproving the Erdős Conjecture with Combinatorial Search",
            "summary": "A counterexample discovered via neural guidance.",
            "publishedAt": "2026-09-04T08:00:00.000Z",
            "authors": [{"name": "Paul Erdős"}, {"name": "Terence Tao"}],
        }
    },
    {
        "paper": {
            "id": "2609.03333",
            "title": "Boolean Satisfiability Solvers in Silicon",
            "summary": "Accelerating hardware verification with clean architectures.",
            "publishedAt": "2026-09-04T09:00:00.000Z",
            "authors": [{"name": "George Boole"}],
        }
    },
    {
        "paper": {
            "id": "2609.04444",
            "title": "Generative Video Modeling for Autonomous Vehicles",
            "summary": "Novel neural network for road scene prediction.",
            "publishedAt": "2026-09-04T11:00:00.000Z",
            "authors": [{"name": "Vehicle Researcher"}],
        }
    },
]


def test_paper_schema():
    """Verify Paper dataclass fields, whitespace normalization, and dictionary support."""
    paper = Paper(
        id="http://arxiv.org/abs/2609.00001",
        title="  A Deep\n  Theorem Prover \n ",
        url="https://arxiv.org/abs/2609.00001",
        authors=[" Alice \n Smith ", " Bob Jones "],
        published="2026-09-05T18:22:00Z",
        summary="  This is a   multiline\n abstract text.  ",
        source="arXiv",
        pillar="architecture",
    )

    assert paper.title == "A Deep Theorem Prover"
    assert paper.summary == "This is a multiline abstract text."
    assert paper.authors == ["Alice Smith", "Bob Jones"]
    assert paper.published == "2026-09-05"
    assert paper["title"] == "A Deep Theorem Prover"
    assert paper["pillar"] == "architecture"

    as_dict = paper.to_dict()
    assert isinstance(as_dict, dict)
    assert as_dict["source"] == "arXiv"


def test_arxiv_xml_parsing():
    """Verify parsing of arXiv XML into Paper objects."""
    papers = parse_arxiv_xml(MOCK_ARXIV_XML, pillar="results")
    assert len(papers) == 2

    p1 = papers[0]
    assert p1.id == "http://arxiv.org/abs/2609.00001v1"
    assert p1.title == "Automated Conjecture Generation with Ramanujan Machines"
    assert p1.url == "https://arxiv.org/abs/2609.00001v1"
    assert p1.authors == ["Alice Lovelace", "Bob Turing"]
    assert p1.published == "2026-09-01"
    assert "combinatorial search" in p1.summary
    assert p1.source == "arXiv"
    assert p1.pillar == "results"

    p2 = papers[1]
    assert p2.id == "http://arxiv.org/abs/2609.00002v1"
    assert p2.title == "Lean 4 Autoformalization Benchmark"
    assert p2.authors == ["Carol Ramanujan"]
    assert p2.published == "2026-09-02"


def test_arxiv_fetch_retry_and_backoff():
    """Verify retry behavior with exponential backoff on transient errors."""
    mock_success = MagicMock()
    mock_success.status_code = 200
    mock_success.text = MOCK_ARXIV_XML
    mock_success.raise_for_status.return_value = None

    # 1. Test recovery on 3rd attempt
    with patch("requests.get", side_effect=[
        requests.RequestException("Timeout 1"),
        requests.RequestException("Timeout 2"),
        mock_success,
    ]):
        papers = fetch_arxiv(pillar="results", max_retries=3, backoff_factor=0.01)
        assert len(papers) == 2

    # 2. Test graceful return of [] after exhausting retries
    with patch("requests.get", side_effect=requests.RequestException("Connection error")):
        papers = fetch_arxiv(pillar="results", max_retries=3, backoff_factor=0.01)
        assert papers == []


def test_huggingface_filtering_and_categorization():
    """Verify keyword filtering and pillar categorization for Hugging Face submissions."""
    # Ensure boolean does not trigger lean keyword
    assert not is_math_relevant("Boolean Satisfiability Solvers in Silicon")
    # Ensure lean triggers keyword
    assert is_math_relevant("Neural reasoning in Lean 4")
    assert is_math_relevant("Advances in formal verification")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_HF_JSON
    mock_resp.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_resp):
        papers = fetch_huggingface(limit=30)

    # Out of 4 mock items: 2 match (AlphaProof -> architecture, Erdős -> results)
    assert len(papers) == 2

    p_arch = next(p for p in papers if p.id == "hf:2609.01111")
    assert p_arch.title == "AlphaProof: Neural Theorem Proving in Lean 4"
    assert p_arch.pillar == "architecture"
    assert p_arch.source == "Hugging Face"
    assert p_arch.url == "https://huggingface.co/papers/2609.01111"
    assert p_arch.authors == ["David Hilbert", "Emmy Noether"]

    p_res = next(p for p in papers if p.id == "hf:2609.02222")
    assert p_res.title == "Disproving the Erdős Conjecture with Combinatorial Search"
    assert p_res.pillar == "results"


def test_huggingface_error_handling():
    """Verify graceful handling of 429, 500, and timeout errors."""
    mock_429 = MagicMock()
    mock_429.status_code = 429

    with patch("requests.get", return_value=mock_429):
        assert fetch_huggingface() == []

    mock_500 = MagicMock()
    mock_500.status_code = 500

    with patch("requests.get", return_value=mock_500):
        assert fetch_huggingface() == []

    with patch("requests.get", side_effect=requests.Timeout("Request timed out")):
        assert fetch_huggingface() == []


def test_aggregator_deduplication():
    """Verify deduplication across sources and pillars by URL and normalized title."""
    paper_arxiv1 = Paper(
        id="http://arxiv.org/abs/2609.00001v1",
        title="Automated Conjecture Generation with Ramanujan Machines",
        url="https://arxiv.org/abs/2609.00001v1",
        authors=["Alice Lovelace"],
        published="2026-09-05",
        summary="Summary A",
        source="arXiv",
        pillar="results",
    )
    # Duplicate of paper 1 with different casing/punctuation in another pillar
    paper_arxiv_dup = Paper(
        id="http://arxiv.org/abs/2609.00001v2",
        title="automated conjecture generation with ramanujan machines!",
        url="https://arxiv.org/abs/2609.00001v2",
        authors=["Alice Lovelace"],
        published="2026-09-05",
        summary="Summary A dup",
        source="arXiv",
        pillar="architecture",
    )
    paper_arxiv2 = Paper(
        id="http://arxiv.org/abs/2609.00002v1",
        title="Lean 4 Autoformalization Benchmark",
        url="https://arxiv.org/abs/2609.00002v1",
        authors=["Carol Ramanujan"],
        published="2026-09-06",
        summary="Summary B",
        source="arXiv",
        pillar="architecture",
    )
    paper_edu = Paper(
        id="http://arxiv.org/abs/2609.00003v1",
        title="Intelligent Tutoring System for Real Analysis",
        url="https://arxiv.org/abs/2609.00003v1",
        authors=["Dan Euler"],
        published="2026-09-06",
        summary="Summary C",
        source="arXiv",
        pillar="education",
    )
    # HF paper with same title as paper 2 -> should be deduplicated
    paper_hf_dup = Paper(
        id="hf:2609.00002",
        title="Lean 4 Autoformalization Benchmark",
        url="https://huggingface.co/papers/2609.00002",
        authors=["Carol Ramanujan"],
        published="2026-09-06",
        summary="HF copy",
        source="Hugging Face",
        pillar="architecture",
    )
    # Unique HF paper
    paper_hf_unique = Paper(
        id="hf:2609.99999",
        title="Novel Neural Proof Search",
        url="https://huggingface.co/papers/2609.99999",
        authors=["Eve Fermat"],
        published="2026-09-07",
        summary="Summary D",
        source="Hugging Face",
        pillar="architecture",
    )

    def mock_arxiv(pillar, max_results=15):
        if pillar == "results":
            return [paper_arxiv1]
        elif pillar == "architecture":
            return [paper_arxiv_dup, paper_arxiv2]
        elif pillar == "education":
            return [paper_edu]
        return []

    def mock_hf(limit=30):
        return [paper_hf_dup, paper_hf_unique]

    agg = aggregator.Aggregator(arxiv_fetcher=mock_arxiv, hf_fetcher=mock_hf, data_dir="")
    result = agg.run()

    assert "updated_at" in result
    assert "pillars" in result
    pillars = result["pillars"]

    # results has paper 1
    assert len(pillars["results"]) == 1
    assert pillars["results"][0].title == "Automated Conjecture Generation with Ramanujan Machines"

    # architecture has paper 2 and paper_hf_unique (paper_arxiv_dup and paper_hf_dup skipped)
    assert len(pillars["architecture"]) == 2
    assert pillars["architecture"][0].title == "Lean 4 Autoformalization Benchmark"
    assert pillars["architecture"][1].title == "Novel Neural Proof Search"

    # education has paper_edu
    assert len(pillars["education"]) == 1
    assert pillars["education"][0].title == "Intelligent Tutoring System for Real Analysis"


def test_aggregator_live_integration():
    """Integration test verifying aggregator.run() against live arXiv and HF endpoints."""
    result = aggregator.run(arxiv_limit=5, hf_limit=10)

    assert "updated_at" in result
    assert "pillars" in result

    pillars = result["pillars"]
    assert "results" in pillars
    assert "architecture" in pillars
    assert "education" in pillars

    # Verify each pillar has non-empty list of Paper instances
    for pillar_name in ["results", "architecture", "education"]:
        paper_list = pillars[pillar_name]
        assert len(paper_list) > 0, f"Expected non-empty list for pillar '{pillar_name}'"
        for paper in paper_list:
            assert isinstance(paper, Paper)
            assert paper.id
            assert paper.title
            assert paper.url
            assert paper.source in {"arXiv", "Hugging Face"}
            assert paper.pillar == pillar_name
