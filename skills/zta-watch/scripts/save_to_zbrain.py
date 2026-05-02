#!/usr/bin/env python3
"""Z Brain integration for /zta-watch — write watch reports to Obsidian.

When --save is passed, the watch report is also written to:
    $Z_BRAIN_PATH/02_reference/video-watches/YYYY-MM-DD-{slug}.md

with Obsidian-friendly frontmatter so bss-qmd can index it for semantic search.

Z_BRAIN_PATH defaults to ~/Documents/Z Brain. Set the env var to override or
disable (point it at a non-existent path to no-op gracefully).
"""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path


SLUG_INVALID = re.compile(r"[^a-z0-9]+")


def zbrain_root() -> Path:
    """Where to save. Honors $Z_BRAIN_PATH; default ~/Documents/Z Brain."""
    raw = os.environ.get("Z_BRAIN_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "Documents" / "Z Brain"


def slugify(title: str, max_len: int = 60) -> str:
    s = title.lower()
    s = SLUG_INVALID.sub("-", s).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "untitled"


def save_report(
    title: str,
    source: str,
    duration_seconds: float,
    uploader: str | None,
    frames_emitted: int,
    frames_deduped: int,
    transcript_source: str | None,
    body_markdown: str,
) -> Path | None:
    """Write the watch report to Z Brain. Returns the file path or None."""
    root = zbrain_root()
    target_dir = root / "02_reference" / "video-watches"
    if not root.exists():
        # Non-BSS user (no Z Brain at expected path). Skip silently.
        return None

    target_dir.mkdir(parents=True, exist_ok=True)

    today = dt.date.today().isoformat()
    slug = slugify(title or "video")
    out = target_dir / f"{today}-{slug}.md"

    # If a file already exists for the same video today, suffix with a counter.
    counter = 1
    while out.exists():
        out = target_dir / f"{today}-{slug}-{counter}.md"
        counter += 1

    duration_str = _format_duration(duration_seconds)
    safe_title = title.replace('"', '\\"')

    frontmatter = (
        "---\n"
        f'title: "{safe_title}"\n'
        f"source: {source}\n"
        f"duration: {duration_str}\n"
        f"uploader: {uploader or 'unknown'}\n"
        f"date_watched: {today}\n"
        f"frames_kept: {frames_emitted}\n"
        f"frames_deduped: {frames_deduped}\n"
        f"transcript_source: {transcript_source or 'none'}\n"
        "tags: [video-watch, reference]\n"
        "---\n\n"
    )

    out.write_text(frontmatter + body_markdown)
    return out


def _format_duration(seconds: float) -> str:
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"
