"""每日调度：APScheduler 定时（默认 08:00 本地时区）运行实时管道。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from ..config import get_settings
from ..ingestion.collect import collect_articles
from .pipeline import run_pipeline

logger = logging.getLogger("analysisdaily")


def daily_job() -> None:
    settings = get_settings()
    articles = collect_articles(settings)
    reports = run_pipeline(articles, settings)
    logger.info("daily job: %d reports", len(reports))


def start_scheduler(hour: int = 8, minute: int = 0) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="Asia/Shanghai")
    sched.add_job(daily_job, "cron", hour=hour, minute=minute)
    sched.start()
    return sched
