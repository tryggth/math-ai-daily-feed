"""Tests for Gemini API editorial brief synthesizer."""

import os
from unittest.mock import MagicMock, patch
import pytest

from src.synthesizer import (
    FALLBACK_API_ERROR,
    FALLBACK_NO_KEY,
    MODEL_NAME,
    SYSTEM_INSTRUCTION_TEMPLATE,
    synthesize_brief,
    _format_candidates_for_pillar,
)
from src.builders.html_builder import build_html
from src.schema import Paper


@pytest.fixture
def sample_data():
    return {
        "updated_at": "2026-09-07T12:00:00Z",
        "pillars": {
            "results": [
                Paper(
                    id="http://arxiv.org/abs/2609.12345v1",
                    title="Novel Counterexample in Extremal Graph Theory",
                    url="https://arxiv.org/abs/2609.12345",
                    authors=["Paul Erdos", "Terence Tao"],
                    published="2026-09-07",
                    summary="Disproved an old conjecture using automated search.",
                    source="arXiv",
                    pillar="results",
                )
            ],
            "architecture": [
                {
                    "id": "hf:2609.54321",
                    "title": "Lean 4 Tactic Predictor",
                    "url": "https://huggingface.co/papers/2609.54321",
                    "authors": ["Ada Lovelace"],
                    "published": "2026-09-07",
                    "summary": "Deep reinforcement learning for Lean 4 formalization.",
                    "source": "Hugging Face",
                    "pillar": "architecture",
                }
            ],
            "education": [],
        },
    }


def test_system_instruction_grounding_constraint():
    """Verify system instruction template enforces strict grounding for AI Connection."""
    assert "**AI Connection:**" in SYSTEM_INSTRUCTION_TEMPLATE
    assert "STRICT GROUNDING RULE" in SYSTEM_INSTRUCTION_TEMPLATE
    assert "Classical symbolic computation / constraint solver (no neural AI)" in SYSTEM_INSTRUCTION_TEMPLATE
    assert "Unspecified AI assistance claimed in abstract; architecture not detailed." in SYSTEM_INSTRUCTION_TEMPLATE


def test_synthesize_brief_missing_api_key(sample_data):
    """Test that missing GEMINI_API_KEY returns fallback and 'none' model without raising exception."""
    with patch.dict(os.environ, {}, clear=True):
        brief, model = synthesize_brief(sample_data)
        assert brief == FALLBACK_NO_KEY
        assert model == "none"


def test_synthesize_brief_empty_api_key(sample_data):
    """Test that empty/whitespace GEMINI_API_KEY returns fallback and 'none' model without raising exception."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "   "}):
        brief, model = synthesize_brief(sample_data)
        assert brief == FALLBACK_NO_KEY
        assert model == "none"


def test_synthesize_brief_mock_success(sample_data):
    """Test that mock API responses return brief markdown and model identifier string."""
    mock_text = """# ☕ Daily Math-AI Brief — 2026-09-07

Today's submissions show strong advances in graph theory counterexamples and interactive theorem proving.

### 1. Mathematical Results via AI
- [Novel Counterexample in Extremal Graph Theory](https://arxiv.org/abs/2609.12345): Solves a long-standing conjecture.
  - **Mathematical Impact:** (Score: 5 — Landmark).
  - **AI Connection:** Classical symbolic computation / constraint solver (no neural AI).

### 2. Theorem Proving & Reasoning Architectures
- [Lean 4 Tactic Predictor](https://huggingface.co/papers/2609.54321): High success rate on miniF2F.
  - **Mathematical Impact:** (Score: 4 — Substantive).
  - **AI Connection:** MCTS tactic search with transformer policy.

### 3. AI in Mathematics Education
No qualifying submissions met the threshold today.
"""

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = mock_text
    mock_client.models.generate_content.return_value = mock_response

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key_123"}):
        with patch("src.synthesizer.genai.Client", return_value=mock_client) as mock_client_cls:
            brief, model_used = synthesize_brief(sample_data)

            mock_client_cls.assert_called_once_with(api_key="fake_test_key_123")
            mock_client.models.generate_content.assert_called_once()
            assert "Daily Math-AI Brief" in brief
            assert "Novel Counterexample" in brief
            assert model_used == MODEL_NAME
            assert f"Synthesized with `{model_used}`" in brief


def test_synthesize_brief_api_error_graceful(sample_data):
    """Test that API exceptions are handled gracefully returning error fallback and 'none'."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("Rate limit exceeded")

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key_123"}):
        with patch("src.synthesizer.genai.Client", return_value=mock_client):
            brief, model_used = synthesize_brief(sample_data)
            assert FALLBACK_API_ERROR in brief
            assert "Rate limit exceeded" in brief
            assert model_used == "none"


def test_format_candidates_for_pillar():
    """Verify candidates formatting for prompt."""
    assert "No candidate papers" in _format_candidates_for_pillar([])
    papers = [{"title": "Test Paper", "authors": ["A", "B"], "url": "https://example.com", "summary": "Abstract"}]
    formatted = _format_candidates_for_pillar(papers)
    assert "Test Paper" in formatted
    assert "A, B" in formatted
    assert "https://example.com" in formatted


def test_html_rendering_with_brief_and_model_badge(tmp_path, sample_data):
    """Verify HTML rendering includes styled editorial brief section and model badge."""
    brief_content = "# ☕ Daily Math-AI Brief\n\nCurated editorial synthesis here."
    html_path = tmp_path / "index.html"

    build_html(
        sample_data,
        output_path=str(html_path),
        brief_md=brief_content,
        model_name="gemini-2.5-flash",
    )

    assert html_path.is_file()
    html_text = html_path.read_text(encoding="utf-8")
    assert '<section class="editorial-brief"' in html_text
    assert "AI Synthesis" in html_text
    assert '<span class="model-badge">Model: gemini-2.5-flash</span>' in html_text
    assert "Curated editorial synthesis here." in html_text


def test_html_rendering_without_brief(tmp_path, sample_data):
    """Verify HTML rendering omits editorial brief section when brief is empty."""
    html_path = tmp_path / "index.html"

    build_html(sample_data, output_path=str(html_path), brief_md="", model_name="")

    assert html_path.is_file()
    html_text = html_path.read_text(encoding="utf-8")
    assert '<section class="editorial-brief"' not in html_text


def test_build_pipeline_saves_brief_in_payload_and_artifacts(tmp_path, sample_data):
    """Verify that build pipeline saves synthesized brief into payload and markdown/html artifacts."""
    import json
    from src.build import main as build_main

    tmp_data_dir = tmp_path / "data"
    tmp_public_dir = tmp_path / "public"
    tmp_data_dir.mkdir()
    tmp_public_dir.mkdir()

    mock_brief_text = "# ☕ Daily Math-AI Brief — 2026-09-07\n\nAI reasoning advance synthesized."
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = mock_brief_text
    mock_client.models.generate_content.return_value = mock_response

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key_123"}):
        with patch("src.synthesizer.genai.Client", return_value=mock_client):
            with patch("src.aggregator.run", return_value=sample_data):
                build_main(output_dir=str(tmp_public_dir), data_dir=str(tmp_data_dir))

    # 1. Verify JSON payload in data/ has editorial_brief and synthesis_metadata
    snapshot_json = tmp_data_dir / "2026-09-07.json"
    assert snapshot_json.is_file()
    with open(snapshot_json, "r", encoding="utf-8") as f:
        data_payload = json.load(f)
    assert "AI reasoning advance synthesized." in data_payload.get("editorial_brief")
    assert "synthesis_metadata" in data_payload
    assert data_payload["synthesis_metadata"]["model"] == MODEL_NAME

    # 2. Verify latest.json has editorial_brief and synthesis_metadata
    latest_json = tmp_public_dir / "latest.json"
    assert latest_json.is_file()
    with open(latest_json, "r", encoding="utf-8") as f:
        latest_payload = json.load(f)
    assert "AI reasoning advance synthesized." in latest_payload.get("editorial_brief")
    assert latest_payload["synthesis_metadata"]["model"] == MODEL_NAME

    # 3. Verify brief.md and data/brief-2026-09-07.md
    assert (tmp_public_dir / "brief.md").is_file()
    assert (tmp_data_dir / "brief-2026-09-07.md").is_file()
    assert f"Synthesized with `{MODEL_NAME}`" in (tmp_public_dir / "brief.md").read_text(encoding="utf-8")

    # 4. Verify index.html renders the brief and model badge
    index_html = (tmp_public_dir / "index.html").read_text(encoding="utf-8")
    assert '<section class="editorial-brief"' in index_html
    assert f'<span class="model-badge">Model: {MODEL_NAME}</span>' in index_html
    assert "AI reasoning advance synthesized." in index_html
