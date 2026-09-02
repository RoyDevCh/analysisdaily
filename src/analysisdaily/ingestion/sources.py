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
    """默认启用的源：真实媒体 RSS（含正文）+ 预留 API 源。每个源=一个 outlet，带独立倾向。"""
    def _w(name, url, bias):  # wire 便捷构造
        return SourceInfo(name=name, url=url, channel=Channel.WIRE, bias=bias, kind="wire", feed_url=url)

    items = [
        # 事实底座流：真实媒体 RSS（含正文，跨 outlet 聚类同一事件）
        _w("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", BiasLabel.CENTER_LEFT),
        _w("The Guardian", "https://www.theguardian.com/world/rss", BiasLabel.LEFT),
        _w("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", BiasLabel.LEFT),
        _w("The Washington Post", "https://feeds.washingtonpost.com/rss/world", BiasLabel.LEFT),
        _w("CNN", "http://rss.cnn.com/rss/edition_world.rss", BiasLabel.CENTER_LEFT),
        _w("NPR", "https://feeds.npr.org/1004/rss.xml", BiasLabel.CENTER_LEFT),
        _w("Fox News", "https://feeds.foxnews.com/foxnews/world", BiasLabel.RIGHT),
        _w("New York Post", "https://nypost.com/feed/", BiasLabel.RIGHT),
        _w("Forbes", "https://www.forbes.com/business/feed/", BiasLabel.CENTER_RIGHT),
        _w("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", BiasLabel.CENTER),
        _w("DW World", "https://rss.dw.com/rdf/rss-en-world", BiasLabel.CENTER),
        # 预留：需要凭据的官方/谱系源
        SourceInfo(name="Ground News", url="https://ground.news", channel=Channel.SPECTRUM, bias=BiasLabel.UNKNOWN, kind="analysis", feed_url=""),
        SourceInfo(name="AllSides", url="https://www.allsides.com", channel=Channel.SPECTRUM, bias=BiasLabel.UNKNOWN, kind="analysis", feed_url=""),
        # 宏观背景
        SourceInfo(name="Pew Research Center", url="https://www.pewresearch.org", channel=Channel.RESEARCH, bias=BiasLabel.CENTER, kind="data", feed_url="https://www.pewresearch.org/feed/"),
        SourceInfo(name="Our World in Data", url="https://ourworldindata.org", channel=Channel.CONTEXT, bias=BiasLabel.CENTER, kind="data", feed_url=""),
    ]
    return items


def find_source(registry: list[SourceInfo], name: str) -> SourceInfo | None:
    for s in registry:
        if s.name == name:
            return s
    return None