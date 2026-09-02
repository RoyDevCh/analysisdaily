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
    # 自定义信源权重：仅影响来源排序（呈现角度），不改动事实
    sw = settings.source_weights or {}
    for r in reports:
        r.sources.sort(key=lambda s: -sw.get(s.name, 0.0))

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
        from ..synthesis.bilingual import localize_zh
        from ..synthesis.daily import build_daily_report, render_daily_report_md

        localize_zh(reports, settings)  # 逐项翻译为中文（在构建日报前）
        daily = build_daily_report(reports, generated_at, source_weights=settings.source_weights)
        # 跨事件深度报道（LLM 执笔，失败回退规则）
        from ..synthesis.feature import write_feature

        items = [it for sec in daily.sections for it in sec.items]
        daily.feature = write_feature(items, settings)
        # 事件追踪：把今天的每条事件并入跨日线程（data/threads.json）
        from ..tracking.threads import load_threads, render_tracking, save_threads, update_threads

        threads_path = settings.app_data_dir / "threads.json"
        _threads = update_threads(embedder, reports, load_threads(threads_path), report_date.strftime("%Y%m%d"))
        save_threads(threads_path, _threads)
        daily.tracking = render_tracking(_threads)
        # 双语：英文版（原生）+ 中文版（整篇 LLM 翻译，实测最可靠）
        from ..synthesis.bilingual import translate_to_zh

        brief_en = render_daily_report_md(daily, lang="en")
        brief_zh = translate_to_zh(settings, brief_en)
        (out_dir / ("daily-" + report_date.isoformat() + ".en.md")).write_text(brief_en, encoding="utf-8")
        (out_dir / ("daily-" + report_date.isoformat() + ".zh.md")).write_text(brief_zh, encoding="utf-8")
        try:
            from ..delivery.dispatch import dispatch

            sent = dispatch(daily, brief_en, brief_zh, settings)
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