"""事件 → 结构化日报条目（StructuredReport）。

护城河一：所有输出经 Pydantic 严格校验；无共分母事实的事件直接放弃，
保证"无证据不发"。
"""
from __future__ import annotations

from datetime import date

from ..facts.package import EventPackage
from ..models.report import SourceRef, StructuredReport


def build_report(pkg: EventPackage, report_date: date, generated_at: str) -> StructuredReport | None:
    # 无任何可核验事实 → 放弃该事件（严格落地）
    if not pkg.verified_facts:
        return None

    # 去重来源
    sources: dict[str, SourceRef] = {}
    for a in pkg.cluster.articles:
        if a.source_name not in sources:
            sources[a.source_name] = SourceRef(name=a.source_name, url=a.url, bias=a.bias)

    return StructuredReport(
        event_id=pkg.cluster.event_cluster_id,
        date=report_date,
        category=pkg.cluster.category,
        headline=pkg.headline,
        verified_facts=pkg.verified_facts,
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