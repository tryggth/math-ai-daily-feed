"""Tests for JSON and HTML artifact builders and build CLI."""

import json
import os
from unittest.mock import patch
import pytest

from src.builders.html_builder import build_html, format_authors, render_html_page
from src.builders.json_builder import build_json
from src.build import main as build_main
from src.schema import Paper


@pytest.fixture
def sample_aggregated_data():
    """Sample aggregated data fixture for builder testing."""
    return {
        "updated_at": "2026-09-06T15:00:00Z",
        "pillars": {
            "results": [
                Paper(
                    id="http://arxiv.org/abs/2609.00010v1",
                    title="Discovery of Counterexample to Borsuk's Conjecture <AI & Search>",
                    url="https://arxiv.org/abs/2609.00010v1",
                    authors=["Alice Euler", "Bob Gauss", "Carol Fermat", "David Hilbert"],
                    published="2026-09-05",
                    summary="Using combinatorial search with <heuristic> guidance.",
                    source="arXiv",
                    pillar="results",
                )
            ],
            "architecture": [
                {
                    "id": "hf:2609.00020",
                    "title": "Lean 4 Reasoning Framework",
                    "url": "https://huggingface.co/papers/2609.00020",
                    "authors": ["Grace Hopper"],
                    "published": "2026-09-04",
                    "summary": "Autoformalization for interactive theorem provers.",
                    "source": "Hugging Face",
                    "pillar": "architecture",
                }
            ],
            "education": [],
        },
    }


def test_build_json_success(tmp_path, sample_aggregated_data):
    """Verify build_json produces formatted, valid JSON with all required keys."""
    json_path = tmp_path / "latest.json"
    build_json(sample_aggregated_data, output_path=str(json_path))

    assert json_path.is_file()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["updated_at"] == "2026-09-06T15:00:00Z"
    assert "pillars" in data
    assert len(data["pillars"]["results"]) == 1
    assert len(data["pillars"]["architecture"]) == 1
    assert len(data["pillars"]["education"]) == 0

    paper = data["pillars"]["results"][0]
    assert paper["id"] == "http://arxiv.org/abs/2609.00010v1"
    assert "Borsuk" in paper["title"]
    assert paper["source"] == "arXiv"


def test_build_json_validation_errors(tmp_path):
    """Verify build_json validates root schema keys."""
    with pytest.raises(ValueError, match="missing required root keys"):
        build_json({"updated_at": "2026-09-06"}, output_path=str(tmp_path / "fail.json"))

    with pytest.raises(ValueError, match="must be a dictionary"):
        build_json(["not", "a", "dict"], output_path=str(tmp_path / "fail.json"))


def test_format_authors_helper():
    """Verify author truncation to 3 authors + 'et al.'."""
    assert format_authors([]) == "Unknown Authors"
    assert format_authors(["One"]) == "One"
    assert format_authors(["One", "Two", "Three"]) == "One, Two, Three"
    assert format_authors(["One", "Two", "Three", "Four", "Five"]) == "One, Two, Three et al."


def test_build_html_rendering_and_escaping(tmp_path, sample_aggregated_data):
    """Verify HTML rendering, XSS escaping, pillar headings, and empty-state handling."""
    html_path = tmp_path / "index.html"
    build_html(sample_aggregated_data, output_path=str(html_path))

    assert html_path.is_file()
    content = html_path.read_text(encoding="utf-8")

    # Verify all 3 pillar headings are present
    assert "Mathematical Results via AI" in content
    assert "Theorem Proving &amp; Reasoning Architecture" in content
    assert "AI in Mathematics Education" in content

    # Verify proper HTML escaping
    assert "&lt;AI &amp; Search&gt;" in content
    assert "<AI & Search>" not in content
    assert "&lt;heuristic&gt;" in content

    # Verify author truncation
    assert "Alice Euler, Bob Gauss, Carol Fermat et al." in content

    # Verify links
    assert 'href="./latest.json"' in content
    assert 'target="_blank"' in content
    assert 'rel="noopener"' in content

    # Verify empty state for education pillar
    assert "No new submissions tracked for this pillar" in content


def test_build_cli_pipeline_and_nojekyll(tmp_path, sample_aggregated_data):
    """Verify build.py CLI execution generates latest.json, index.html, and .nojekyll."""
    with patch("src.aggregator.run", return_value=sample_aggregated_data):
        build_main(output_dir=str(tmp_path))

    json_file = tmp_path / "latest.json"
    html_file = tmp_path / "index.html"
    nojekyll_file = tmp_path / ".nojekyll"

    assert json_file.is_file()
    assert html_file.is_file()
    assert nojekyll_file.is_file()

    assert json_file.stat().st_size > 0
    assert html_file.stat().st_size > 0
    assert nojekyll_file.stat().st_size == 0
