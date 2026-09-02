"""抓取适配器。

- RssSourceAdapter：用 requests（带超时/UA）+ feedparser 抓通用 RSS（公开、无 key）。
- ApiSourceAdapter：预留基类，供 Ground News / Reuters / AP / OWID 官方接口接入。
- 通过 settings 判断哪些需要凭据的源可启用（有 key 才启用）。
"""
from __future__ import annotations

import hashlib
import urllib.request
from datetime import datetime, timezone

import feedparser  # type: ignore

from ..config import Settings
from ..models.raw import RawArticle, SourceInfo
from .outlets import outlet_bias
from .sources import build_default_registry

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)


def _slug(text: str, n: int = 48) -> str:
    import re

    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.lower()).strip("-")
    return s[:n]


class RssSourceAdapter:
    """通用 RSS 抓取 → RawArticle。"""

    def __init__(self, source: SourceInfo, max_items: int = 30, timeout: int = 15):
        self.source = source
        self.max_items = max_items
        self.timeout = timeout

    def fetch(self) -> list[RawArticle]:
        if not self.source.feed_url:
            return []
        req = urllib.request.Request(self.source.feed_url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            content = resp.read()
        feed = feedparser.parse(content)
        out: list[RawArticle] = []
        for entry in feed.entries[: self.max_items]:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            content = summary
            for c in entry.get("content") or []:
                if c.get("value"):
                    content = c["value"]
                    break
            published = _parse_published(entry)
            # Google News 等 feed 的每条目带真实媒体名（<source>），据此决定来源与倾向
            item_src = entry.get("source") or {}
            outlet = (item_src.get("title") or "").strip()
            bias = outlet_bias(outlet) if outlet else self.source.bias
            src_name = outlet if outlet else self.source.name
            src_url = (item_src.get("href") or "").strip() or link
            rid = _article_id(src_name, src_url, published)
            out.append(
                RawArticle(
                    id=rid,
                    source_name=src_name,
                    channel=self.source.channel,
                    bias=bias,
                    side=bias.side,
                    title=title,
                    url=src_url,
                    published=published,
                    summary=summary,
                    content=content,
                    feed=self.source.name,
                )
            )
        return out


class ApiSourceAdapter:
    """预留：官方/授权 API 接入基类。"""

    def __init__(self, source: SourceInfo, settings: Settings):
        self.source = source
        self.settings = settings

    def available(self) -> bool:
        raise NotImplementedError

    def fetch(self) -> list[RawArticle]:
        raise NotImplementedError


class GroundNewsAdapter(ApiSourceAdapter):
    def _key(self) -> str:
        return self.settings.ground_news_api_key

    def available(self) -> bool:
        return bool(self._key())

    def fetch(self) -> list[RawArticle]:
        # 填 GROUND_NEWS_API_KEY 后实现：提取左右中报道比例。
        return []


class AllSidesAdapter(ApiSourceAdapter):
    def _key(self) -> str:
        return self.settings.allsides_api_key

    def available(self) -> bool:
        return bool(self._key())

    def fetch(self) -> list[RawArticle]:
        return []


class WireApiAdapter(ApiSourceAdapter):
    """预留：Reuters / AP 官方授权接口（News API / Reuters Connect）。"""

    def _key(self) -> str:
        return self.settings.wire_earth_api_key

    def available(self) -> bool:
        return bool(self._key())

    def fetch(self) -> list[RawArticle]:
        return []


def _parse_published(entry) -> datetime:
    ts = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if ts:
        # feedparser 返回 time.struct_time（UTC），无 .timestamp()
        return datetime(*ts[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _article_id(source: str, url: str, published: datetime) -> str:
    raw = f"{source}|{url}|{published.strftime('%Y%m%d%H%M')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_adapters(settings: Settings, registry: list[SourceInfo] | None = None) -> list:
    """构建当前可用的适配器列表。

    公开 RSS 源始终启用；需凭据的源仅在有 key 时启用（API 适配器）。
    返回 (adapter, source) 元组。
    """
    registry = registry or build_default_registry()
    api_by_name = {
        "Ground News": lambda s, st: GroundNewsAdapter(s, st),
        "AllSides": lambda s, st: AllSidesAdapter(s, st),
    }
    adapters: list = []
    for src in registry:
        if src.kind in ("wire", "data") and src.feed_url:
            adapters.append((RssSourceAdapter(src), src))
        else:
            ap = api_by_name.get(src.name)
            if ap:
                inst = ap(src, settings)
                if inst.available():
                    adapters.append((inst, src))
    return adapters