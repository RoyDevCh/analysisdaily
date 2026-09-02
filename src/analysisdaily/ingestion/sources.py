"""数据源注册表。

按需求三层抓取流（三类通道）建模，每个源带 bias 标签与可信度权重。
MVP 阶段默认启用**公开可抓取**的源；需要凭据的官方源（Reuters/AP API、
Ground News/AllSides）作为"预留适配器"，在有 key 时自动启用。

- 诚实说明：直接抓取 Reuters/AP 站点正文可能违反其使用条款（ToS/robots），
  因此 MVP 用 Google News 公共 RSS 作为"电讯社事实底座"的公开代理，
  官方授权接口通过 adapter 预留，未来填 key 即接入。
"""
from __future__ import annotations

from ..models.raw import Channel, SourceInfo
from ..models.report import BiasLabel


def google_news_rss(query: str) -> str:
    """Google News 公开 RSS（无需 key）。作为公开的电讯社/事实源代理。"""
    from urllib.parse import quote

    return f"https://news.google.com/rss/search?q={quote(query)}"


def build_default_registry() -> list[SourceInfo]:
    """默认启用的源。按通道归类。"""
    return [
        # ---- 事实底座流（Wire）：主题级查询，同一事件的多源覆盖；每条目按真实媒体标注倾向 ----
        SourceInfo(
            name="Google News · 经济市场",
            url="https://news.google.com",
            channel=Channel.WIRE,
            bias=BiasLabel.CENTER,
            kind="wire",
            feed_url=google_news_rss("stock market OR economy when:1d"),
        ),
        SourceInfo(
            name="Google News · 科技",
            url="https://news.google.com",
            channel=Channel.WIRE,
            bias=BiasLabel.CENTER,
            kind="wire",
            feed_url=google_news_rss("artificial intelligence OR technology when:1d"),
        ),
        SourceInfo(
            name="Google News · 气候环境",
            url="https://news.google.com",
            channel=Channel.WIRE,
            bias=BiasLabel.CENTER,
            kind="wire",
            feed_url=google_news_rss("climate change OR energy when:1d"),
        ),
        SourceInfo(
            name="Google News · 国际冲突",
            url="https://news.google.com",
            channel=Channel.WIRE,
            bias=BiasLabel.CENTER,
            kind="wire",
            feed_url=google_news_rss("conflict OR war OR sanctions when:1d"),
        ),
        SourceInfo(
            name="BBC World (public RSS)",
            url="https://feeds.bbci.co.uk/news/world/rss.xml",
            channel=Channel.WIRE,
            bias=BiasLabel.CENTER_LEFT,
            kind="wire",
            feed_url="https://feeds.bbci.co.uk/news/world/rss.xml",
        ),
        # ---- 舆论光谱流（Spectrum，需要 key，MVP 预留禁用）----
        SourceInfo(
            name="Ground News",
            url="https://ground.news",
            channel=Channel.SPECTRUM,
            bias=BiasLabel.UNKNOWN,
            kind="analysis",
            feed_url="",   # 需 GROUND_NEWS_API_KEY
        ),
        SourceInfo(
            name="AllSides",
            url="https://www.allsides.com",
            channel=Channel.SPECTRUM,
            bias=BiasLabel.UNKNOWN,
            kind="analysis",
            feed_url="",   # 需 ALLSIDES_API_KEY
        ),
        # ---- 宏观背景流（Context / Research，公开）----
        SourceInfo(
            name="Pew Research Center",
            url="https://www.pewresearch.org",
            channel=Channel.RESEARCH,
            bias=BiasLabel.CENTER,
            kind="data",
            feed_url="https://www.pewresearch.org/feed/",
        ),
        SourceInfo(
            name="Our World in Data",
            url="https://ourworldindata.org",
            channel=Channel.CONTEXT,
            bias=BiasLabel.CENTER,
            kind="data",
            feed_url="",
        ),
    ]


def find_source(registry: list[SourceInfo], name: str) -> SourceInfo | None:
    for s in registry:
        if s.name == name:
            return s
    return None