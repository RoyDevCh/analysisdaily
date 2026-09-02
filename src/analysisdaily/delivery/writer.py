"""本地落盘：把日报 JSON / Markdown 写入 data/reports/。"""
from __future__ import annotations

from pathlib import Path

from ..models.report import StructuredReport
from ..synthesis.render import render_json, render_markdown


def write_report(
    r: StructuredReport, out_dir: Path, ext: str = "both"
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / r.event_id
    paths: dict[str, Path] = {}
    if ext in ("json", "both"):
        p = base.with_suffix(".json")
        p.write_text(render_json(r), encoding="utf-8")
        paths["json"] = p
    if ext in ("md", "both"):
        p = base.with_suffix(".md")
        p.write_text(render_markdown(r), encoding="utf-8")
        paths["md"] = p
    return paths


def write_daily_index(reports: list[StructuredReport], out_dir: Path) -> Path:
    from ..synthesis.render import render_daily_markdown

    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = reports[0].date.isoformat() if reports else "no-date"
    path = out_dir / f"daily-{date_str}.md"
    path.write_text(render_daily_markdown(reports, date_str), encoding="utf-8")
    return path
