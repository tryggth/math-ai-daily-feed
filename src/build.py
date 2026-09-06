"""CLI build pipeline orchestrating aggregation, persistent archiving, and artifact generation."""

from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Optional

from src import aggregator
from src.builders.html_builder import build_html
from src.builders.json_builder import build_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("build")


def main(
    output_dir: str = "public",
    data_dir: str = "data",
    arxiv_limit: int = 15,
    hf_limit: int = 30,
) -> None:
    """Run full build pipeline with persistent data archiving and archive rendering."""
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    logger.info("Starting AI in Mathematics Daily Feed build & archive pipeline...")

    # 1. Fetch fresh aggregated data
    logger.info("Aggregating papers from arXiv and Hugging Face...")
    data = aggregator.run(arxiv_limit=arxiv_limit, hf_limit=hf_limit)

    # 2. Determine today's date stamp (YYYY-MM-DD)
    updated_at = data.get("updated_at", "")
    if len(updated_at) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", updated_at[:10]):
        today_str = updated_at[:10]
    else:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 3. Save today's snapshot to data/{YYYY-MM-DD}.json
    today_data_path = os.path.join(data_dir, f"{today_str}.json")
    logger.info("Archiving current run snapshot to %s...", today_data_path)
    build_json(data, output_path=today_data_path)

    # 4. Scan data/ for all *.json files to create a sorted date index (newest first)
    all_json_files = [f for f in os.listdir(data_dir) if f.endswith(".json")]
    available_dates = sorted(
        [f[:-5] for f in all_json_files if re.match(r"^\d{4}-\d{2}-\d{2}$", f[:-5])],
        reverse=True,
    )
    if not available_dates:
        available_dates = [today_str]

    logger.info("Found %d archived editions: %s", len(available_dates), available_dates)

    # 5. Create public/archive/ directory
    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    # 6. For every historical date in data/:
    #    - Export public/archive/{date}.json
    #    - Render public/archive/{date}.html
    for date_str in available_dates:
        source_file = os.path.join(data_dir, f"{date_str}.json")
        with open(source_file, "r", encoding="utf-8") as f:
            edition_data = json.load(f)

        archive_json_path = os.path.join(archive_dir, f"{date_str}.json")
        archive_html_path = os.path.join(archive_dir, f"{date_str}.html")

        build_json(edition_data, output_path=archive_json_path)
        build_html(
            edition_data,
            output_path=archive_html_path,
            available_dates=available_dates,
            current_date=date_str,
            is_archive=True,
        )

    # 7. The newest date is exported as public/latest.json and public/index.html
    latest_date = available_dates[0]
    latest_source_file = os.path.join(data_dir, f"{latest_date}.json")
    with open(latest_source_file, "r", encoding="utf-8") as f:
        latest_data = json.load(f)

    latest_json_path = os.path.join(output_dir, "latest.json")
    latest_html_path = os.path.join(output_dir, "index.html")

    build_json(latest_data, output_path=latest_json_path)
    build_html(
        latest_data,
        output_path=latest_html_path,
        available_dates=available_dates,
        current_date=latest_date,
        is_archive=False,
    )

    # 8. Create empty public/.nojekyll
    nojekyll_path = os.path.join(output_dir, ".nojekyll")
    with open(nojekyll_path, "w", encoding="utf-8") as f:
        pass

    # 9. Print summary metrics
    pillars = latest_data.get("pillars", {})
    results_count = len(pillars.get("results", []))
    arch_count = len(pillars.get("architecture", []))
    edu_count = len(pillars.get("education", []))
    total_count = results_count + arch_count + edu_count

    print("\n" + "=" * 60)
    print("      AI IN MATHEMATICS DAILY FEED — BUILD SUMMARY      ")
    print("=" * 60)
    print(f"Latest Edition:  {latest_date} ({latest_data.get('updated_at')})")
    print(f"Total Papers:    {total_count}")
    print(f"Archived Runs:   {len(available_dates)} edition(s)")
    print("Breakdown (Latest):")
    print(f"  • Mathematical Results via AI:             {results_count:>3} papers")
    print(f"  • Theorem Proving & Reasoning Architecture: {arch_count:>3} papers")
    print(f"  • AI in Mathematics Education:             {edu_count:>3} papers")
    print("-" * 60)
    print("Generated Artifacts:")
    print(f"  • {latest_json_path}")
    print(f"  • {latest_html_path}")
    print(f"  • {archive_dir}/* ({len(available_dates) * 2} files)")
    print(f"  • {nojekyll_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
