"""HTML artifact builder rendering responsive single-page digest with historical date picker."""

import html
import logging
import os
import tempfile
from typing import Any, Optional

logger = logging.getLogger(__name__)

PILLARS_METADATA = [
    {
        "key": "results",
        "title": "Mathematical Results via AI",
        "description": "Empirical discoveries, counterexamples, Ramanujan machines, and automated conjecture generation.",
        "badge_color": "#10b981",
    },
    {
        "key": "architecture",
        "title": "Theorem Proving & Reasoning Architecture",
        "description": "Formal verification, Lean 4, autoformalization, premise selection, and neuro-symbolic reasoning.",
        "badge_color": "#8b5cf6",
    },
    {
        "key": "education",
        "title": "AI in Mathematics Education",
        "description": "Intelligent tutoring systems, step-by-step mathematical reasoning, and pedagogical AI tools.",
        "badge_color": "#f59e0b",
    },
]


def format_authors(authors: list[str]) -> str:
    """Format and truncate author list to 3 authors + 'et al.'."""
    if not authors:
        return "Unknown Authors"
    cleaned = [a.strip() for a in authors if a and a.strip()]
    if not cleaned:
        return "Unknown Authors"
    if len(cleaned) > 3:
        return ", ".join(cleaned[:3]) + " et al."
    return ", ".join(cleaned)


def _get_field(item: Any, key: str, default: Any = "") -> Any:
    """Retrieve attribute or dict key seamlessly."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def render_paper_card(paper: Any) -> str:
    """Render a single responsive card component for a paper."""
    title = str(_get_field(paper, "title", "Untitled"))
    url = str(_get_field(paper, "url", "#"))
    raw_authors = _get_field(paper, "authors", [])
    authors = list(raw_authors) if isinstance(raw_authors, (list, tuple)) else []
    published = str(_get_field(paper, "published", ""))
    summary = str(_get_field(paper, "summary", ""))
    source = str(_get_field(paper, "source", "arXiv"))

    escaped_title = html.escape(title)
    escaped_url = html.escape(url, quote=True)
    escaped_authors = html.escape(format_authors(authors))
    escaped_published = html.escape(published[:10] if published else "Recent")
    escaped_summary = html.escape(summary)
    escaped_source = html.escape(source)

    source_class = "badge-hf" if "hugging" in source.lower() else "badge-arxiv"

    return f"""        <article class="paper-card">
          <div class="card-header">
            <span class="source-badge {source_class}">{escaped_source}</span>
            <time class="pub-date">{escaped_published}</time>
          </div>
          <h3 class="paper-title">
            <a href="{escaped_url}" target="_blank" rel="noopener">{escaped_title}</a>
          </h3>
          <p class="paper-authors">{escaped_authors}</p>
          <details class="abstract-details">
            <summary class="abstract-toggle">View Abstract</summary>
            <p class="abstract-text">{escaped_summary}</p>
          </details>
        </article>"""


def render_html_page(
    aggregated_data: dict[str, Any],
    available_dates: Optional[list[str]] = None,
    current_date: Optional[str] = None,
    is_archive: bool = False,
) -> str:
    """Generate complete self-contained HTML5 string with historical date selector."""
    updated_at = str(aggregated_data.get("updated_at", "Just now"))
    escaped_updated_at = html.escape(updated_at)
    raw_pillars = aggregated_data.get("pillars", {})
    pillars = raw_pillars if isinstance(raw_pillars, dict) else {}

    # Normalize available_dates and current_date
    if not available_dates:
        fallback_date = updated_at[:10] if len(updated_at) >= 10 else "Today"
        available_dates = [current_date or fallback_date]
    if not current_date:
        current_date = available_dates[0]

    # Generate options for date-picker dropdown
    options_parts = []
    for idx, d in enumerate(available_dates):
        selected_attr = " selected" if d == current_date else ""
        if idx == 0:
            label = f"Latest ({d})"
            val = "../index.html" if is_archive else "./index.html"
        else:
            label = d
            val = f"./{d}.html" if is_archive else f"archive/{d}.html"
        options_parts.append(
            f'<option value="{html.escape(val, quote=True)}"{selected_attr}>{html.escape(label)}</option>'
        )
    options_html = "\n            ".join(options_parts)

    # Dynamic JSON endpoint link
    if is_archive:
        json_url = f"./{current_date}.json"
        json_label = f"{current_date}.json"
    else:
        json_url = "./latest.json"
        json_label = "latest.json"

    sections_html = []
    total_papers = 0

    for meta in PILLARS_METADATA:
        key = meta["key"]
        title = meta["title"]
        desc = meta["description"]
        papers = pillars.get(key, [])
        count = len(papers)
        total_papers += count

        if papers:
            cards = "\n".join(render_paper_card(p) for p in papers)
            content_html = f"""      <div class="cards-grid">
{cards}
      </div>"""
        else:
            content_html = """      <div class="empty-state">
        <p>No new submissions tracked for this pillar in the current cycle.</p>
      </div>"""

        section_block = f"""    <section class="pillar-section" id="{html.escape(key)}">
      <div class="section-header">
        <div>
          <h2 class="section-title">{html.escape(title)}</h2>
          <p class="section-desc">{html.escape(desc)}</p>
        </div>
        <span class="count-pill">{count} paper{'s' if count != 1 else ''}</span>
      </div>
{content_html}
    </section>"""
        sections_html.append(section_block)

    all_sections = "\n\n".join(sections_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="dark light">
  <title>AI in Mathematics Daily Feed</title>
  <meta name="description" content="Daily intelligence digest tracking AI breakthroughs, theorem proving architectures, and mathematical education tools.">
  <style>
    :root {{
      color-scheme: dark light;
      --bg-canvas: #090d16;
      --bg-surface: #111827;
      --bg-surface-elevated: #1e293b;
      --border-subtle: #1f293d;
      --border-focus: #38bdf8;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --text-faint: #64748b;
      --accent-primary: #38bdf8;
      --accent-hover: #7dd3fc;
      --arxiv-bg: #1e293b;
      --arxiv-text: #93c5fd;
      --hf-bg: #312111;
      --hf-text: #fcd34d;
      --shadow-card: 0 4px 6px -1px rgba(0, 0, 0, 0.25), 0 2px 4px -2px rgba(0, 0, 0, 0.25);
    }}

    @media (prefers-color-scheme: light) {{
      :root {{
        --bg-canvas: #f8fafc;
        --bg-surface: #ffffff;
        --bg-surface-elevated: #f1f5f9;
        --border-subtle: #e2e8f0;
        --border-focus: #0284c7;
        --text-main: #0f172a;
        --text-muted: #475569;
        --text-faint: #64748b;
        --accent-primary: #0284c7;
        --accent-hover: #0369a1;
        --arxiv-bg: #eff6ff;
        --arxiv-text: #1d4ed8;
        --hf-bg: #fef3c7;
        --hf-text: #b45309;
        --shadow-card: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
      }}
    }}

    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--bg-canvas);
      color: var(--text-main);
      line-height: 1.5;
      padding: 2rem 1rem;
      min-height: 100vh;
    }}

    .container {{
      max-width: 1200px;
      margin: 0 auto;
    }}

    header.main-header {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 2rem;
      margin-bottom: 2.5rem;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1.5rem;
      box-shadow: var(--shadow-card);
    }}

    .header-title-group h1 {{
      font-size: 1.875rem;
      font-weight: 700;
      letter-spacing: -0.025em;
      margin-bottom: 0.35rem;
    }}

    .header-title-group p {{
      color: var(--text-muted);
      font-size: 0.95rem;
      max-width: 650px;
    }}

    .header-actions {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 0.75rem;
    }}

    .nav-controls {{
      display: flex;
      align-items: center;
      gap: 0.65rem;
      flex-wrap: wrap;
    }}

    .date-picker-label {{
      font-size: 0.8rem;
      color: var(--text-muted);
      font-weight: 500;
    }}

    .date-selector {{
      background: var(--bg-surface-elevated);
      color: var(--text-main);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 0.45rem 0.75rem;
      font-size: 0.85rem;
      font-weight: 500;
      cursor: pointer;
      outline: none;
      transition: border-color 0.15s ease;
    }}

    .date-selector:hover, .date-selector:focus {{
      border-color: var(--border-focus);
    }}

    .timestamp-badge {{
      font-size: 0.8rem;
      color: var(--text-faint);
    }}

    .api-pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: var(--accent-primary);
      color: #ffffff;
      padding: 0.45rem 0.9rem;
      border-radius: 9999px;
      text-decoration: none;
      font-weight: 600;
      font-size: 0.85rem;
      transition: background 0.15s ease, transform 0.1s ease;
    }}

    .api-pill:hover {{
      background: var(--accent-hover);
      transform: translateY(-1px);
    }}

    .pillar-section {{
      margin-bottom: 3rem;
    }}

    .section-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      margin-bottom: 1.25rem;
      padding-bottom: 0.75rem;
      border-bottom: 2px solid var(--border-subtle);
      gap: 1rem;
    }}

    .section-title {{
      font-size: 1.35rem;
      font-weight: 600;
      letter-spacing: -0.015em;
      margin-bottom: 0.25rem;
    }}

    .section-desc {{
      font-size: 0.875rem;
      color: var(--text-muted);
    }}

    .count-pill {{
      background: var(--bg-surface-elevated);
      color: var(--text-muted);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.25rem 0.65rem;
      border-radius: 9999px;
      white-space: nowrap;
      border: 1px solid var(--border-subtle);
    }}

    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
      gap: 1.25rem;
    }}

    @media (max-width: 640px) {{
      .cards-grid {{
        grid-template-columns: 1fr;
      }}
      header.main-header {{
        padding: 1.25rem;
        flex-direction: column;
        align-items: flex-start;
      }}
      .header-actions {{
        align-items: flex-start;
      }}
    }}

    .paper-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      box-shadow: var(--shadow-card);
      transition: border-color 0.15s ease, transform 0.15s ease;
    }}

    .paper-card:hover {{
      border-color: var(--border-focus);
      transform: translateY(-2px);
    }}

    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
    }}

    .source-badge {{
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
    }}

    .badge-arxiv {{
      background: var(--arxiv-bg);
      color: var(--arxiv-text);
    }}

    .badge-hf {{
      background: var(--hf-bg);
      color: var(--hf-text);
    }}

    .pub-date {{
      font-size: 0.75rem;
      color: var(--text-faint);
    }}

    .paper-title {{
      font-size: 1rem;
      font-weight: 600;
      line-height: 1.4;
      margin-bottom: 0.5rem;
    }}

    .paper-title a {{
      color: var(--text-main);
      text-decoration: none;
      transition: color 0.15s ease;
    }}

    .paper-title a:hover {{
      color: var(--accent-primary);
    }}

    .paper-authors {{
      font-size: 0.825rem;
      color: var(--text-muted);
      margin-bottom: 0.85rem;
    }}

    .abstract-details {{
      margin-top: auto;
      border-top: 1px solid var(--border-subtle);
      padding-top: 0.65rem;
    }}

    .abstract-toggle {{
      font-size: 0.775rem;
      font-weight: 600;
      color: var(--accent-primary);
      cursor: pointer;
      user-select: none;
      outline: none;
    }}

    .abstract-toggle:hover {{
      color: var(--accent-hover);
    }}

    .abstract-text {{
      font-size: 0.825rem;
      color: var(--text-muted);
      margin-top: 0.5rem;
      line-height: 1.5;
    }}

    .empty-state {{
      background: var(--bg-surface);
      border: 1px dashed var(--border-subtle);
      border-radius: 8px;
      padding: 2rem;
      text-align: center;
      color: var(--text-faint);
      font-size: 0.9rem;
    }}

    footer.main-footer {{
      margin-top: 4rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border-subtle);
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-faint);
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="main-header">
      <div class="header-title-group">
        <h1>AI in Mathematics Daily Feed</h1>
        <p>Automated intelligence tracking empirical results, formal theorem proving architectures, and mathematics education systems.</p>
      </div>
      <div class="header-actions">
        <div class="nav-controls">
          <label for="date-picker" class="date-picker-label">Edition:</label>
          <select id="date-picker" class="date-selector" aria-label="Select feed date">
            {options_html}
          </select>
          <a href="{html.escape(json_url, quote=True)}" class="api-pill" target="_blank" rel="noopener">
            <span>&lt;/&gt;</span> {html.escape(json_label)}
          </a>
        </div>
        <span class="timestamp-badge">Updated: {escaped_updated_at}</span>
      </div>
    </header>

    <main>
{all_sections}
    </main>

    <footer class="main-footer">
      <p>Generated by AI in Mathematics Daily Feed pipeline &bull; Tracking {total_papers} papers across 3 pillars</p>
    </footer>
  </div>

  <script>
    const datePicker = document.getElementById('date-picker');
    if (datePicker) {{
      datePicker.addEventListener('change', function() {{
        window.location.href = this.value;
      }});
    }}
  </script>
</body>
</html>
"""


def build_html(
    aggregated_data: dict[str, Any],
    output_path: str = "public/index.html",
    available_dates: Optional[list[str]] = None,
    current_date: Optional[str] = None,
    is_archive: bool = False,
) -> None:
    """Build and write single-page HTML artifact atomically."""
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)

    content = render_html_page(
        aggregated_data,
        available_dates=available_dates,
        current_date=current_date,
        is_archive=is_archive,
    )

    tmp_file = tempfile.NamedTemporaryFile(
        "w", dir=output_dir, delete=False, suffix=".tmp", encoding="utf-8"
    )
    tmp_path = tmp_file.name

    try:
        with tmp_file as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, output_path)
        logger.info("Successfully wrote HTML artifact to %s", output_path)
    except Exception as exc:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        logger.error("Failed to write HTML artifact to %s: %s", output_path, exc)
        raise
