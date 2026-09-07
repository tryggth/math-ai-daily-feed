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
from src.synthesizer import synthesize_brief

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
    data = aggregator.run(arxiv_limit=arxiv_limit, hf_limit=hf_limit, data_dir=data_dir)

    # 2. Determine today's date stamp (YYYY-MM-DD)
    updated_at = data.get("updated_at", "")
    if len(updated_at) >= 10 and re.match(r"^\d{4}-\d{2}-\d{2}", updated_at[:10]):
        today_str = updated_at[:10]
    else:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 3. Generate daily AI editorial brief using Gemini API
    logger.info("Synthesizing daily editorial brief via Gemini API...")
    brief_md, model_name = synthesize_brief(data)
    data["editorial_brief"] = brief_md
    today_iso = datetime.now(timezone.utc).isoformat()
    data["synthesis_metadata"] = {"model": model_name, "generated_at": today_iso}

    # Save public/brief.md and data/brief-{date}.md
    today_brief_path = os.path.join(data_dir, f"brief-{today_str}.md")
    with open(today_brief_path, "w", encoding="utf-8") as f:
        f.write(brief_md)

    public_brief_path = os.path.join(output_dir, "brief.md")
    with open(public_brief_path, "w", encoding="utf-8") as f:
        f.write(brief_md)

    # 4. Save today's snapshot to data/{YYYY-MM-DD}.json
    today_data_path = os.path.join(data_dir, f"{today_str}.json")
    logger.info("Archiving current run snapshot to %s...", today_data_path)
    build_json(data, output_path=today_data_path)

    # 5. Scan data/ for all *.json files to create a sorted date index (newest first)
    all_json_files = [f for f in os.listdir(data_dir) if f.endswith(".json")]
    available_dates = sorted(
        [f[:-5] for f in all_json_files if re.match(r"^\d{4}-\d{2}-\d{2}$", f[:-5])],
        reverse=True,
    )
    if not available_dates:
        available_dates = [today_str]

    logger.info("Found %d archived editions: %s", len(available_dates), available_dates)

    # 6. Create public/archive/ directory
    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    # 7. For every historical date in data/:
    #    - Export public/archive/{date}.json
    #    - Render public/archive/{date}.html
    for date_str in available_dates:
        source_file = os.path.join(data_dir, f"{date_str}.json")
        with open(source_file, "r", encoding="utf-8") as f:
            edition_data = json.load(f)

        edition_brief = edition_data.get("editorial_brief", "")
        edition_model = edition_data.get("synthesis_metadata", {}).get("model", "")
        if not edition_brief:
            archived_brief_file = os.path.join(data_dir, f"brief-{date_str}.md")
            if os.path.isfile(archived_brief_file):
                with open(archived_brief_file, "r", encoding="utf-8") as bf:
                    edition_brief = bf.read()

        archive_json_path = os.path.join(archive_dir, f"{date_str}.json")
        archive_html_path = os.path.join(archive_dir, f"{date_str}.html")

        build_json(edition_data, output_path=archive_json_path)
        build_html(
            edition_data,
            output_path=archive_html_path,
            available_dates=available_dates,
            current_date=date_str,
            is_archive=True,
            brief_md=edition_brief,
            model_name=edition_model,
        )

    # 8. The newest date is exported as public/latest.json and public/index.html
    latest_date = available_dates[0]
    latest_source_file = os.path.join(data_dir, f"{latest_date}.json")
    with open(latest_source_file, "r", encoding="utf-8") as f:
        latest_data = json.load(f)

    latest_brief = latest_data.get("editorial_brief", "")
    latest_model = latest_data.get("synthesis_metadata", {}).get("model", "")
    if not latest_brief:
        latest_brief_file = os.path.join(data_dir, f"brief-{latest_date}.md")
        if os.path.isfile(latest_brief_file):
            with open(latest_brief_file, "r", encoding="utf-8") as bf:
                latest_brief = bf.read()
    if not latest_brief and latest_date == today_str:
        latest_brief = brief_md
    if not latest_model and latest_date == today_str:
        latest_model = model_name

    latest_json_path = os.path.join(output_dir, "latest.json")
    latest_html_path = os.path.join(output_dir, "index.html")

    build_json(latest_data, output_path=latest_json_path)
    build_html(
        latest_data,
        output_path=latest_html_path,
        available_dates=available_dates,
        current_date=latest_date,
        is_archive=False,
        brief_md=latest_brief,
        model_name=latest_model,
    )

    # 9. Create empty public/.nojekyll
    nojekyll_path = os.path.join(output_dir, ".nojekyll")
    with open(nojekyll_path, "w", encoding="utf-8") as f:
        pass

    # 10. Print summary metrics
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
    print(f"  • {public_brief_path}")
    print(f"  • {today_brief_path}")
    print(f"  • {archive_dir}/* ({len(available_dates) * 2} files)")
    print(f"  • {nojekyll_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
