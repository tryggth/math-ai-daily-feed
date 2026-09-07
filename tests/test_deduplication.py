"""Tests for historical cross-day deduplication and preprint freshness filtering."""

from datetime import date, datetime, timezone
import json
import pytest

from src import aggregator
from src.aggregator import (
    extract_arxiv_id,
    is_fresh,
    load_historical_seen_identifiers,
)
from src.schema import Paper


def test_extract_arxiv_id():
    """Verify extraction of canonical arXiv ID without versions or prefixes."""
    assert extract_arxiv_id("http://arxiv.org/abs/2609.04170v2") == "2609.04170"
    assert extract_arxiv_id("https://huggingface.co/papers/2609.04170") == "2609.04170"
    assert extract_arxiv_id("hf:2609.04170") == "2609.04170"
    assert extract_arxiv_id("2609.04170") == "2609.04170"
    assert extract_arxiv_id("non-arxiv-id") == ""


def test_is_fresh_window():
    """Verify that papers older than max_age_days are rejected, while recent ones pass."""
    ref_date = date(2026, 9, 7)

    # Today / yesterday / within 5 days
    assert is_fresh("2026-09-07", max_age_days=5, reference_date=ref_date)
    assert is_fresh("2026-09-06T12:00:00Z", max_age_days=5, reference_date=ref_date)
    assert is_fresh("2026-09-02", max_age_days=5, reference_date=ref_date)  # exactly 5 days

    # Older than 5 days
    assert not is_fresh("2026-09-01", max_age_days=5, reference_date=ref_date)  # 6 days
    assert not is_fresh("2026-08-20", max_age_days=5, reference_date=ref_date)  # 18 days

    # Future paper (within 1 day timezone buffer vs far future)
    assert is_fresh("2026-09-08", max_age_days=5, reference_date=ref_date)
    assert not is_fresh("2026-09-20", max_age_days=5, reference_date=ref_date)

    # Malformed / empty dates
    assert not is_fresh("", max_age_days=5, reference_date=ref_date)
    assert not is_fresh("invalid-date", max_age_days=5, reference_date=ref_date)


def test_load_historical_seen_identifiers(tmp_path):
    """Verify loading and normalizing identifiers from historical data snapshots."""
    hist_snapshot = {
        "updated_at": "2026-09-01T12:00:00Z",
        "pillars": {
            "results": [
                {
                    "id": "http://arxiv.org/abs/2609.00100v1",
                    "title": "On Ramanujan Continued Fractions",
                    "url": "https://arxiv.org/abs/2609.00100v1",
                }
            ],
            "architecture": [
                {
                    "id": "hf:2609.00200",
                    "title": "Interactive Proof Assistants in Lean",
                    "url": "https://huggingface.co/papers/2609.00200",
                }
            ],
        },
    }

    file_path = tmp_path / "2026-09-01.json"
    file_path.write_text(json.dumps(hist_snapshot), encoding="utf-8")

    seen = load_historical_seen_identifiers(str(tmp_path))

    # URLs
    assert "https://arxiv.org/abs/2609.00100" in seen
    assert "https://huggingface.co/papers/2609.00200" in seen

    # Normalized titles
    assert "on ramanujan continued fractions" in seen
    assert "interactive proof assistants in lean" in seen

    # arXiv IDs
    assert "arxiv:2609.00100" in seen
    assert "arxiv:2609.00200" in seen


def test_cross_day_historical_deduplication(tmp_path):
    """Verify papers matching IDs in a temporary historical snapshot are excluded from aggregation."""
    # 1. Populate data/2026-09-01.json with a historical paper
    hist_data = {
        "updated_at": "2026-09-01T12:00:00Z",
        "pillars": {
            "results": [
                {
                    "id": "http://arxiv.org/abs/2609.00099v1",
                    "title": "Historical Counterexample To Conjecture",
                    "url": "https://arxiv.org/abs/2609.00099v1",
                    "authors": ["Old Author"],
                    "published": "2026-09-01",
                    "summary": "Old summary",
                    "source": "arXiv",
                    "pillar": "results",
                }
            ],
            "architecture": [],
            "education": [],
        },
    }
    (tmp_path / "2026-09-01.json").write_text(json.dumps(hist_data), encoding="utf-8")

    # 2. Mock candidate papers for today: one duplicate (historical), one novel
    dup_paper = Paper(
        id="http://arxiv.org/abs/2609.00099v2",
        title="Historical Counterexample to Conjecture!",
        url="https://arxiv.org/abs/2609.00099v2",
        authors=["Old Author"],
        published="2026-09-06",
        summary="Updated revision",
        source="arXiv",
        pillar="results",
    )
    novel_paper = Paper(
        id="http://arxiv.org/abs/2609.00888v1",
        title="Brand New Mathematical Discovery",
        url="https://arxiv.org/abs/2609.00888v1",
        authors=["New Author"],
        published="2026-09-06",
        summary="Novel summary",
        source="arXiv",
        pillar="results",
    )

    def mock_arxiv(pillar, max_results=15):
        if pillar == "results":
            return [dup_paper, novel_paper]
        return []

    agg = aggregator.Aggregator(
        arxiv_fetcher=mock_arxiv,
        hf_fetcher=lambda limit=30: [],
        data_dir=str(tmp_path),
    )
    result = agg.run(data_dir=str(tmp_path), current_date="2026-09-07")

    results_pillar = result["pillars"]["results"]
    titles = [p.title for p in results_pillar]

    # Duplicate must be filtered out
    assert "Historical Counterexample to Conjecture!" not in titles
    # Novel paper must be present
    assert "Brand New Mathematical Discovery" in titles
    assert len(results_pillar) == 1


def test_stale_paper_filtering(tmp_path):
    """Verify papers published > 5 days ago are filtered out even if never seen."""
    stale_paper = Paper(
        id="http://arxiv.org/abs/2608.00001v1",
        title="Very Old Preprint",
        url="https://arxiv.org/abs/2608.00001v1",
        authors=["Author Stale"],
        published="2026-08-15",  # 23 days ago
        summary="Summary stale",
        source="arXiv",
        pillar="results",
    )
    fresh_paper = Paper(
        id="http://arxiv.org/abs/2609.00555v1",
        title="Fresh Contemporary Preprint",
        url="https://arxiv.org/abs/2609.00555v1",
        authors=["Author Fresh"],
        published="2026-09-06",  # 1 day ago
        summary="Summary fresh",
        source="arXiv",
        pillar="results",
    )

    def mock_arxiv(pillar, max_results=15):
        if pillar == "results":
            return [stale_paper, fresh_paper]
        return []

    agg = aggregator.Aggregator(
        arxiv_fetcher=mock_arxiv,
        hf_fetcher=lambda limit=30: [],
        data_dir=str(tmp_path),
    )
    result = agg.run(
        data_dir=str(tmp_path),
        reference_date=date(2026, 9, 7),
        max_age_days=5,
    )

    results_pillar = result["pillars"]["results"]
    titles = [p.title for p in results_pillar]

    assert "Very Old Preprint" not in titles
    assert "Fresh Contemporary Preprint" in titles
    assert len(results_pillar) == 1


def test_same_day_rerun_preserves_candidates(tmp_path):
    """Verify running aggregation when today's snapshot already exists does not reject today's papers."""
    today_str = "2026-09-07"
    today_paper = Paper(
        id="http://arxiv.org/abs/2609.00777v1",
        title="Today Theorem Proving Breakthrough",
        url="https://arxiv.org/abs/2609.00777v1",
        authors=["Today Author"],
        published=today_str,
        summary="Summary today",
        source="arXiv",
        pillar="architecture",
    )

    # Pre-populate today's snapshot
    today_data = {
        "updated_at": f"{today_str}T10:00:00Z",
        "pillars": {
            "results": [],
            "architecture": [today_paper.to_dict()],
            "education": [],
        },
    }
    (tmp_path / f"{today_str}.json").write_text(json.dumps(today_data), encoding="utf-8")

    def mock_arxiv(pillar, max_results=15):
        if pillar == "architecture":
            return [today_paper]
        return []

    agg = aggregator.Aggregator(
        arxiv_fetcher=mock_arxiv,
        hf_fetcher=lambda limit=30: [],
        data_dir=str(tmp_path),
    )
    result = agg.run(data_dir=str(tmp_path), current_date=today_str)

    arch_pillar = result["pillars"]["architecture"]
    assert len(arch_pillar) == 1
    assert arch_pillar[0].title == "Today Theorem Proving Breakthrough"
