"""CLI build pipeline orchestrating aggregation, artifact generation, and deployment prep."""

import logging
import os
import sys
from typing import Optional

from src import aggregator
from src.builders.html_builder import build_html
from src.builders.json_builder import build_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("build")


def main(output_dir: str = "public", arxiv_limit: int = 15, hf_limit: int = 30) -> None:
    """Run the complete build pipeline: fetch data, write artifacts, and generate .nojekyll."""
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Starting AI in Mathematics Daily Feed build pipeline...")

    # 1. Fetch and aggregate data
    logger.info("Aggregating papers from arXiv and Hugging Face...")
    data = aggregator.run(arxiv_limit=arxiv_limit, hf_limit=hf_limit)

    json_path = os.path.join(output_dir, "latest.json")
    html_path = os.path.join(output_dir, "index.html")
    nojekyll_path = os.path.join(output_dir, ".nojekyll")

    # 2. Build JSON
    logger.info("Generating JSON API at %s...", json_path)
    build_json(data, output_path=json_path)

    # 3. Build HTML
    logger.info("Generating HTML interface at %s...", html_path)
    build_html(data, output_path=html_path)

    # 4. Create .nojekyll
    logger.info("Creating GitHub Pages .nojekyll marker at %s...", nojekyll_path)
    with open(nojekyll_path, "w", encoding="utf-8") as f:
        pass

    # 5. Print summary metrics
    pillars = data.get("pillars", {})
    results_count = len(pillars.get("results", []))
    arch_count = len(pillars.get("architecture", []))
    edu_count = len(pillars.get("education", []))
    total_count = results_count + arch_count + edu_count

    print("\n" + "=" * 60)
    print("      AI IN MATHEMATICS DAILY FEED — BUILD SUMMARY      ")
    print("=" * 60)
    print(f"Timestamp:       {data.get('updated_at')}")
    print(f"Total Papers:    {total_count}")
    print("Breakdown:")
    print(f"  • Mathematical Results via AI:             {results_count:>3} papers")
    print(f"  • Theorem Proving & Reasoning Architecture: {arch_count:>3} papers")
    print(f"  • AI in Mathematics Education:             {edu_count:>3} papers")
    print("-" * 60)
    print("Generated Artifacts:")
    print(f"  • {json_path}")
    print(f"  • {html_path}")
    print(f"  • {nojekyll_path}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
