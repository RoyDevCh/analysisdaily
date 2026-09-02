"""摄取编排：跑所有可用适配器 → 去重 → 输出原始文章列表。"""
from __future__ import annotations

import logging

from ..config import Settings
from ..models.raw import RawArticle
from .adapters import build_adapters


def _dedup(articles: list[RawArticle]) -> list[RawArticle]:
    seen: dict[str, RawArticle] = {}
    for a in articles:
        k = a.dedup_key()
        # 同标题同源同时刻视为重复；保留正文/摘要更长的一篇
        prev = seen.get(k)
        if prev is None or len(a.text) > len(prev.text):
            seen[k] = a
    return list(seen.values())


def collect_articles(settings: Settings) -> list[RawArticle]:
    """从所有可用适配器拉取文章并去重。

    公开 RSS 始终尝试；网络不可用或源不可达时返回空/可用的子集，
    不影响后续用样本夹具跑通管道。
    """
    articles: list[RawArticle] = []
    adapters = build_adapters(settings)
    for adapter, _source in adapters:
        try:
            got = adapter.fetch()
            articles.extend(got)
        except Exception:
            logging.getLogger(__name__).warning("adapter %s 失败，跳过", _source.name, exc_info=True)
            continue
    return _dedup(articles)