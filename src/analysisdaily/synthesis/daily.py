""""日报"聚合层：把逐条事件合成一份可读的、按主题分组的每日简报。

目标：不是"新闻列表"，而是"一份日报"——先今日综述，再按主题分组，
每条精炼为一句话（标题 + 核心事实 + 分歧/盲区），最后汇总报道盲区。
默认只展开"印证度最高"的前 N 条，其余收进"其它事件"一行式。
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from ..models.report import StructuredReport

MAX_ITEMS = 12  # 主报告展开的事件数上限


class DailyItem(BaseModel):
    headline: str
    event_id: str
    category: str
    summary: str = ""
    left_focus: str = ""
    right_focus: str = ""
    blindspot: str = ""
    single_source: bool = False
    source_count: int = 0
    coverage: str = ""


class CategorySection(BaseModel):
    category: str
    items: list[DailyItem] = Field(default_factory=list)


class DailyReport(BaseModel):
    date: date
    event_count: int = 0
    shown_count: int = 0
    source_total: int = 0
    lead_paragraph: str = ""
    top_stories: list[DailyItem] = Field(default_factory=list)
    sections: list[CategorySection] = Field(default_factory=list)
    more_items: list[DailyItem] = Field(default_factory=list)
    reporting_gaps: list[str] = Field(default_factory=list)
    generated_at: str = ""
    feature: str = ""


def _to_item(r: StructuredReport) -> DailyItem:
    facts = r.verified_facts
    single_ratio = sum(1 for f in facts if f.single_source_claim) / max(1, len(facts))
    return DailyItem(
        headline=r.headline, event_id=r.event_id, category=r.category,
        summary=(r.summary or "").strip(),
        left_focus=r.perspectives_divergence.left_leaning_focus or "",
        right_focus=r.perspectives_divergence.right_leaning_focus or "",
        blindspot=r.perspectives_divergence.blindspot_warning or "",
        single_source=single_ratio > 0.5,
        source_count=r.raw_article_count,
        coverage=(
            f"中心 {r.perspectives_divergence.center_coverage} / 左 {r.perspectives_divergence.left_coverage} / "
            f"右 {r.perspectives_divergence.right_coverage}"
        ),
    )


def _item_score(it: DailyItem) -> tuple:
    # 印证度：来源多且非"单方"靠前
    return (-it.source_count, it.single_source)


def _lead_paragraph(daily: DailyReport) -> str:
    cats = "、".join(s.category for s in daily.sections[:3])
    top = daily.top_stories[0].headline if daily.top_stories else ""
    tail = daily.top_stories[1].headline if len(daily.top_stories) > 1 else ""
    if daily.top_stories and len(daily.top_stories) > 1:
        return (
            f"今日共汇总 {daily.event_count} 条事件，来自 {daily.source_total} 篇报道，聚焦 {cats} 等领域。"
            f"最受关注：{top}、{tail}。已过滤情绪词并仅保留带引文接地的事实，左右翼分歧与报道盲区见各条目。"
        )
    return f"今日共汇总 {daily.event_count} 条事件，来自 {daily.source_total} 篇报道，聚焦 {cats} 等领域。"


def build_daily_report(reports: list[StructuredReport], generated_at: str, max_items: int = MAX_ITEMS) -> DailyReport:
    items = [_to_item(r) for r in reports]
    items.sort(key=_item_score)
    shown = items[:max_items]
    more = items[max_items:]

    by_cat: dict[str, list[DailyItem]] = {}
    for it in shown:
        by_cat.setdefault(it.category, []).append(it)
    sections = []
    for cat, cat_items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        cat_items = sorted(cat_items, key=_item_score)
        sections.append(CategorySection(category=cat, items=cat_items))

    gaps: list[str] = []
    for r in reports:
        g = r.perspectives_divergence.blindspot_warning
        if g and g not in gaps and "样本过少" not in g:
            gaps.append(g)

    daily = DailyReport(
        date=reports[0].date if reports else datetime.now(timezone.utc).date(),
        event_count=len(reports),
        shown_count=len(shown),
        source_total=sum(r.raw_article_count for r in reports),
        top_stories=shown[:5],
        sections=sections,
        more_items=more,
        reporting_gaps=gaps[:6],
        generated_at=generated_at,
    )
    daily.lead_paragraph = _lead_paragraph(daily)
    return daily


def _item_line(it: DailyItem) -> str:
    flag = " ⚠单方" if it.single_source else ""
    lines = [f"### {it.headline}{flag}（{it.source_count} 来源 | {it.coverage}）"]
    if it.summary:
        lines.append(it.summary.strip())
    focus = []
    if it.left_focus:
        focus.append(f"左翼：{it.left_focus}")
    if it.right_focus:
        focus.append(f"右翼：{it.right_focus}")
    if it.blindspot:
        focus.append(f"盲区：{it.blindspot}")
    if focus:
        lines.append("  " + "；".join(focus))
    return "\n".join(lines)


def render_daily_report_md(daily: DailyReport) -> str:
    lines = [f"# 中立客观日报 · {daily.date.isoformat()}", "", daily.lead_paragraph, ""]
    if daily.feature:
        lines.append("## 深度报道")
        for para in daily.feature.split("\n\n"):
            if para.strip():
                lines.append(para.strip())
        lines.append("")
    if daily.top_stories:
        lines.append("## 今日要点")
        for it in daily.top_stories:
            lines.append(_item_line(it))
        lines.append("")
    for sec in daily.sections:
        lines.append(f"## {sec.category}（{len(sec.items)}）")
        for it in sec.items:
            lines.append(_item_line(it))
        lines.append("")
    if daily.more_items:
        lines.append(f"## 其它事件（{len(daily.more_items)}）")
        for it in daily.more_items:
            lines.append(f"- {it.headline}（{it.source_count} 来源）")
        lines.append("")
    if daily.reporting_gaps:
        lines.append("## 报道盲区")
        for g in daily.reporting_gaps:
            lines.append(f"- {g}")
        lines.append("")
    lines.append("> 生成引擎：规则/LLM 兜底；每条事实均带引文接地；无共分母证据已被过滤。")
    return "\n".join(lines)