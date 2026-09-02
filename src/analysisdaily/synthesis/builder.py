"""事件 → 结构化日报条目（StructuredReport）。

护城河一：所有输出经 Pydantic 严格校验；无共分母事实的事件直接放弃，
保证"无证据不发"。
"""
from __future__ import annotations

from datetime import date

from ..facts.package import EventPackage
from ..facts.subjectivity import is_clean_fact
from ..models.report import SourceRef, StructuredReport


def build_report(pkg: EventPackage, report_date: date, generated_at: str) -> StructuredReport | None:
    # 无任何可核验事实 → 放弃该事件（严格落地）
    if not pkg.verified_facts:
        return None

    # 护城河：过滤不合格事实（含情绪词/感叹号），绝不因单条事实导致整批失败
    facts = [f for f in pkg.verified_facts if is_clean_fact(f.text)]
    if not facts:
        return None

    # 去重来源
    sources: dict[str, SourceRef] = {}
    for a in pkg.cluster.articles:
        if a.source_name not in sources:
            sources[a.source_name] = SourceRef(name=a.source_name, url=a.url, bias=a.bias)

    # 护城河：headline 也不能含情绪词/感叹号，否则回退到干净标题
    headline = pkg.headline
    if not is_clean_fact(headline):
        headline = (facts[0].text[:120] if facts else pkg.cluster.headline_hint[:120])
    return StructuredReport(
        event_id=pkg.cluster.event_cluster_id,
        date=report_date,
        category=pkg.cluster.category,
        headline=headline,
        summary=pkg.summary,
        headline_zh=getattr(pkg, "headline_zh", ""),
        summary_zh=getattr(pkg, "summary_zh", ""),
        left_focus_zh=getattr(pkg, "left_focus_zh", ""),
        right_focus_zh=getattr(pkg, "right_focus_zh", ""),
        blindspot_zh=getattr(pkg, "blindspot_zh", ""),
        verified_facts=facts,
        perspectives_divergence=pkg.divergence,
        background_data=pkg.background,
        sources=list(sources.values()),
        event_cluster_id=pkg.cluster.event_cluster_id,
        engine=pkg.engine,
        generated_at=generated_at,
        raw_article_count=pkg.cluster.size,
    )


def build_daily(packages: list[EventPackage], report_date: date, generated_at: str) -> list[StructuredReport]:
    reports = []
    for pkg in packages:
        rep = build_report(pkg, report_date, generated_at)
        if rep is not None:
            reports.append(rep)
    return reports