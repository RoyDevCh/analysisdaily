""""日报"聚合层：把逐条事件合成一份可读的、按主题分组的每日简报。

目标：不是"新闻列表"，而是"一份日报"——先今日综述，再按主题分组，
每条精炼为一句话（标题 + 核心事实 + 分歧/盲区），最后汇总报道盲区。
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from ..models.report import StructuredReport


class DailyItem(BaseModel):
    headline: str
    event_id: str
    category: str
    key_fact: str = ""
    single_source: bool = False
    divergence_note: str = ""
    source_count: int = 0
    coverage: str = ""


class CategorySection(BaseModel):
    category: str
    items: list[DailyItem] = Field(default_factory=list)


class DailyReport(BaseModel):
    date: date
    event_count: int = 0
    source_total: int = 0
    lead_paragraph: str = ""
    top_stories: list[DailyItem] = Field(default_factory=list)
    sections: list[CategorySection] = Field(default_factory=list)
    reporting_gaps: list[str] = Field(default_factory=list)
    generated_at: str = ""


def _to_item(r: StructuredReport) -> DailyItem:
    facts = r.verified_facts
    key_fact = ""
    if facts:
        # 优先取"多源共认"的事实，其次取可信度最高的一条
        canonical = next((f for f in facts if not f.single_source_claim), facts[0])
        key_fact = canonical.text.strip()
        if len(key_fact) > 160:
            key_fact = key_fact[:157].rstrip() + "..."
    single_ratio = sum(1 for f in facts if f.single_source_claim) / max(1, len(facts))
    div = r.perspectives_divergence
    note = ""
    for candidate in (div.blindspot_warning, div.left_leaning_focus, div.right_leaning_focus):
        if candidate and "基本未报道" not in candidate and "样本过少" not in candidate and "无偏见" not in candidate:
            note = candidate
            break
    return DailyItem(
        headline=r.headline,
        event_id=r.event_id,
        category=r.category,
        key_fact=key_fact,
        single_source=single_ratio > 0.5,
        divergence_note=note,
        source_count=r.raw_article_count,
        coverage=(
            f"中心 {r.perspectives_divergence.center_coverage} / "
            f"左 {r.perspectives_divergence.left_coverage} / "
            f"右 {r.perspectives_divergence.right_coverage}"
        ),
    )


def _lead_paragraph(daily: DailyReport, top_items: list[DailyItem]) -> str:
    cats = "、".join(daily.sections[i].category for i in range(min(3, len(daily.sections))))
    top = top_items[0].headline if top_items else ""
    tail = top_items[1].headline if len(top_items) > 1 else ""
    if top_items and len(top_items) > 1:
        return (
            f"今日共汇总 {daily.event_count} 条事件，来自 {daily.source_total} 篇报道，"
            f"聚焦 {cats} 等领域。最受关注：{top}、{tail}。"
            f"本期已过滤情绪词并仅保留带引文接地的事实，左右翼分歧与报道盲区见各条目。"
        )
    return (
        f"今日共汇总 {daily.event_count} 条事件，来自 {daily.source_total} 篇报道，聚焦 {cats} 等领域。"
        f"本期已过滤情绪词并仅保留带引文接地的事实。"
    )


def build_daily_report(reports: list[StructuredReport], generated_at: str) -> DailyReport:
    items = [_to_item(r) for r in reports]
    # 按类别分组
    by_cat: dict[str, list[DailyItem]] = {}
    for it in items:
        by_cat.setdefault(it.category, []).append(it)
    sections = []
    for cat, cat_items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        cat_items = sorted(cat_items, key=lambda i: (-i.source_count, -len(i.key_fact)))
        sections.append(CategorySection(category=cat, items=cat_items))

    top_items = sorted(items, key=lambda i: (-i.source_count, -len(i.key_fact)))[:5]

    # 汇总盲区（去重）
    gaps: list[str] = []
    for r in reports:
        g = r.perspectives_divergence.blindspot_warning
        if g and g not in gaps and "样本过少" not in g:
            gaps.append(g)

    daily = DailyReport(
        date=reports[0].date if reports else datetime.now(timezone.utc).date(),
        event_count=len(reports),
        source_total=sum(r.raw_article_count for r in reports),
        top_stories=top_items,
        sections=sections,
        reporting_gaps=gaps[:6],
        generated_at=generated_at,
    )
    daily.lead_paragraph = _lead_paragraph(daily, top_items)
    return daily


def _item_line(it: DailyItem) -> str:
    flag = " ⚠单方" if it.single_source else ""
    note = f" — {it.divergence_note}" if it.divergence_note else ""
    return f"- **{it.headline}**{flag} （{it.source_count} 来源 | {it.coverage}）\n  {it.key_fact}{note}".rstrip()


def render_daily_report_md(daily: DailyReport) -> str:
    lines = [f"# 中立客观日报 · {daily.date.isoformat()}", "", daily.lead_paragraph, ""]
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
    if daily.reporting_gaps:
        lines.append("## 报道盲区")
        for g in daily.reporting_gaps:
            lines.append(f"- {g}")
        lines.append("")
    lines.append("> 生成引擎：规则/LLM 兜底；每条事实均带引文接地；无共分母证据已被过滤。")
    return "\n".join(lines)