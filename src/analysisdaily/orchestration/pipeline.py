"""端到端管道：文章 → 聚类 → 事实/偏见 → 结构化日报 → 落盘。"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from ..clustering.clusterer import HdbscanClusterer
from ..clustering.embedder import Embedder
from ..config import Settings
from ..delivery.writer import write_report

logger = logging.getLogger("analysisdaily")
from ..facts.engine import get_fact_engine
from ..models.raw import RawArticle
from ..models.report import StructuredReport
from ..synthesis.builder import build_daily


def run_pipeline(
    articles: list[RawArticle],
    settings: Settings,
    report_date: date | None = None,
    out_dir: Path | None = None,
    embedder: Embedder | None = None,
) -> tuple[list[StructuredReport], object]:
    report_date = report_date or _derive_date(articles)
    out_dir = out_dir or (settings.app_data_dir / "reports")
    embedder = embedder or Embedder(settings)
    date_str = report_date.strftime("%Y%m%d")

    clusterer = HdbscanClusterer(
        embedder,
        window_hours=settings.cluster_window_hours,
        min_samples=settings.cluster_min_samples,
    )
    clusters = clusterer.cluster(articles, date_str)

    engine = get_fact_engine(settings, embedder)
    packages = [engine.analyze(c) for c in clusters]

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    reports = build_daily(packages, report_date, generated_at)

    # 可选：本地 docker 容器（pgvector）持久化元数据/日报
    try:
        from ..storage.db import get_db

        db = get_db(settings)
        if db.connect():
            for a in articles:
                db.store_article(a)
            for r in reports:
                db.store_report(r)
            db.close()
            logger.info("persisted %d articles / %d reports to Postgres", len(articles), len(reports))
    except Exception:
        logger.warning("postgres persist skipped", exc_info=True)

    for r in reports:
        write_report(r, out_dir)
    daily = None
    if reports:
        from ..synthesis.daily import build_daily_report, render_daily_report_md

        daily = build_daily_report(reports, generated_at)
        # 跨事件深度报道（LLM 执笔，失败回退规则）
        from ..synthesis.feature import write_feature

        items = [it for sec in daily.sections for it in sec.items]
        daily.feature = write_feature(items, settings)
        brief_md = render_daily_report_md(daily)
        (out_dir / ("daily-" + report_date.isoformat() + ".md")).write_text(brief_md, encoding="utf-8")
        # 分发：推送"一篇"可读日报
        try:
            from ..delivery.dispatch import dispatch

            sent = dispatch(daily, brief_md, settings)
            if any(sent.values()):
                logger.info("dispatch: %s", {k: v for k, v in sent.items() if v})
        except Exception:
            logger.warning("dispatch failed", exc_info=True)
    return reports, daily


def _derive_date(articles: list[RawArticle]) -> date:
    if articles:
        latest = max(a.published for a in articles)
        return latest.date()
    return datetime.now(timezone.utc).date()