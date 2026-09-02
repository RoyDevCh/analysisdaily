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

CATEGORY_EN = {
    "国际政治": "International Politics", "经济与市场": "Economy & Markets", "科技与AI": "Tech & AI",
    "气候与环境": "Climate & Environment", "安全与冲突": "Security & Conflict", "社会与公共政策": "Society & Policy",
    "文化体育": "Culture & Sports", "未分类": "Uncategorized",
}


class DailyItem(BaseModel):
    headline: str
    event_id: str
    category: str
    summary: str = ""
    summary_zh: str = ""
    left_focus: str = ""
    left_zh: str = ""
    right_focus: str = ""
    right_zh: str = ""
    blindspot: str = ""
    blindspot_zh: str = ""
    headline_zh: str = ""
    single_source: bool = False
    source_count: int = 0
    coverage: str = ""
    preferred_sources: list[str] = Field(default_factory=list)


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
    feature_zh: str = ""
    lead_zh: str = ""
    tracking: list[str] = Field(default_factory=list)


def _to_item(r: StructuredReport, source_weights: dict | None = None) -> DailyItem:
    facts = r.verified_facts
    single_ratio = sum(1 for f in facts if f.single_source_claim) / max(1, len(facts))
    source_weights = source_weights or {}
    pref = [
        s.name for s in sorted(r.sources, key=lambda s: -source_weights.get(s.name, 0.0))
        if source_weights.get(s.name, 0.0) > 0
    ][:3]
    return DailyItem(
        headline=r.headline, event_id=r.event_id, category=r.category,
        preferred_sources=pref,
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


def _lead_paragraph_zh(daily: DailyReport) -> str:
    cats = "、".join(s.category for s in daily.sections[:3])
    top = daily.top_stories[0].headline_zh or daily.top_stories[0].headline if daily.top_stories else ""
    tail = (daily.top_stories[1].headline_zh or daily.top_stories[1].headline) if len(daily.top_stories) > 1 else ""
    if daily.top_stories and len(daily.top_stories) > 1:
        return (f"今日共汇总 {daily.event_count} 条事件，来自 {daily.source_total} 篇报道，聚焦 {cats} 等领域。最受关注：{top}；{tail}。已过滤情绪词并仅保留带引文接地的事实。")
    return f"今日共汇总 {daily.event_count} 条事件，来自 {daily.source_total} 篇报道，聚焦 {cats} 等领域。"


def _lead_paragraph(daily: DailyReport) -> str:
    cats = "、".join(CATEGORY_EN.get(s.category, s.category) for s in daily.sections[:3])
    top = daily.top_stories[0].headline if daily.top_stories else ""
    tail = daily.top_stories[1].headline if len(daily.top_stories) > 1 else ""
    if daily.top_stories and len(daily.top_stories) > 1:
        return (
            f"Today's digest covers {daily.event_count} events from {daily.source_total} sources, focusing on "
            f"{cats}. Most covered: {top}; {tail}. Emotive language is filtered and every fact is quote-grounded."
        )
    return f"Today's digest covers {daily.event_count} events from {daily.source_total} sources, focusing on {cats}."


def build_daily_report(reports: list[StructuredReport], generated_at: str, max_items: int = MAX_ITEMS, source_weights: dict | None = None) -> DailyReport:
    items = [_to_item(r, source_weights) for r in reports]
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
    daily.lead_zh = _lead_paragraph_zh(daily)
    return daily


def _item_line(it: DailyItem, lang: str = "zh") -> str:
    en = lang == "en"
    flag = " ⚠单方" if it.single_source else ""
    head = it.headline_zh if (not en and it.headline_zh) else it.headline
    body = it.summary_zh if (not en and it.summary_zh) else it.summary
    lines = [f"### {head}{flag}（{it.source_count} 来源 | {it.coverage}）"]
    if body:
        lines.append(body.strip())
    if it.preferred_sources:
        lines.append("  \U0001f4cc 偏好信源：" + "、".join(it.preferred_sources))
    focus = []
    left = it.left_zh if (not en and it.left_zh) else it.left_focus
    right = it.right_zh if (not en and it.right_zh) else it.right_focus
    blind = it.blindspot_zh if (not en and it.blindspot_zh) else it.blindspot
    if left:
        focus.append(f"左翼：{left}")
    if right:
        focus.append(f"右翼：{right}")
    if blind:
        focus.append(f"盲区：{blind}")
    if focus:
        lines.append("  " + "；".join(focus))
    return "\n".join(lines)


def render_daily_report_md(daily: DailyReport, lang: str = "zh") -> str:
    en = lang == "en"
    _cat = lambda c: (CATEGORY_EN.get(c, c) if en else c)
    title = f"Neutral Daily Report · {daily.date.isoformat()}" if en else f"中立客观日报 · {daily.date.isoformat()}"
    lead = daily.lead_zh if (not en and daily.lead_zh) else daily.lead_paragraph
    feat = daily.feature_zh if (not en and daily.feature_zh) else daily.feature
    lines = [f"# {title}", "", lead, ""]
    if feat:
        lines.append("## 深度报道")
        for para in feat.split("\n\n"):
            if para.strip():
                lines.append(para.strip())
        lines.append("")
    if daily.tracking:
        lines.append("## " + ("Event Tracking (cross-day timeline)" if en else "事件追踪（跨日时间线）"))
        lines.extend(daily.tracking)
        lines.append("")
    if daily.top_stories:
        lines.append("## 今日要点")
        for it in daily.top_stories:
            lines.append(_item_line(it, lang))
        lines.append("")
    for sec in daily.sections:
        lines.append(f"## {_cat(sec.category)}（{len(sec.items)}）")
        for it in sec.items:
            lines.append(_item_line(it, lang))
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