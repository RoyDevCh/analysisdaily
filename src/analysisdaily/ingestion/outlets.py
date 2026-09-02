"""媒体名 → 政治倾向 映射（用于给 Google News 主题流里的每条新闻打上真实来源与倾向）。

让"同一事件的多源覆盖"能正确聚类、并获得左右光谱；避免把整批归为一个"来源"。
未知媒体 → Unknown（不计入左右，但仍是独立来源，可交叉核验）。
"""
from __future__ import annotations

from ..models.report import BiasLabel

# 小写媒体名/域名关键词 → 倾向
_map: dict[str, BiasLabel] = {
    # 事实底座（中心）
    "reuters": BiasLabel.CENTER,
    "reuters.com": BiasLabel.CENTER,
    "the associated press": BiasLabel.CENTER,
    "associated press": BiasLabel.CENTER,
    "ap news": BiasLabel.CENTER,
    "ap": BiasLabel.CENTER,
    "bloomberg": BiasLabel.CENTER,
    "cnbc": BiasLabel.CENTER,
    "usa today": BiasLabel.CENTER,
    "cbs news": BiasLabel.CENTER,
    "abc news": BiasLabel.CENTER,
    "the hill": BiasLabel.CENTER,
    "politico": BiasLabel.CENTER,
    "axios": BiasLabel.CENTER,
    "al jazeera": BiasLabel.CENTER,
    "dw": BiasLabel.CENTER,
    "france24": BiasLabel.CENTER,
    # 中左
    "bbc": BiasLabel.CENTER_LEFT,
    "bbc news": BiasLabel.CENTER_LEFT,
    "cnn": BiasLabel.CENTER_LEFT,
    "nbc news": BiasLabel.CENTER_LEFT,
    "npr": BiasLabel.CENTER_LEFT,
    "the economist": BiasLabel.CENTER_LEFT,
    # 左
    "the guardian": BiasLabel.LEFT,
    "guardian": BiasLabel.LEFT,
    "the new york times": BiasLabel.LEFT,
    "new york times": BiasLabel.LEFT,
    "the washington post": BiasLabel.LEFT,
    "washington post": BiasLabel.LEFT,
    "the atlantic": BiasLabel.LEFT,
    "msnbc": BiasLabel.LEFT,
    "huffpost": BiasLabel.LEFT,
    # 中右
    "the wall street journal": BiasLabel.CENTER_RIGHT,
    "wall street journal": BiasLabel.CENTER_RIGHT,
    "wsj": BiasLabel.CENTER_RIGHT,
    "financial times": BiasLabel.CENTER_RIGHT,
    "the telegraph": BiasLabel.CENTER_RIGHT,
    "forbes": BiasLabel.CENTER_RIGHT,
    "the times": BiasLabel.CENTER_RIGHT,
    # 右
    "fox news": BiasLabel.RIGHT,
    "fox": BiasLabel.RIGHT,
    "the daily wire": BiasLabel.RIGHT,
    "breitbart": BiasLabel.RIGHT,
    "newsmax": BiasLabel.RIGHT,
    "new york post": BiasLabel.RIGHT,
    "washington times": BiasLabel.RIGHT,
    "the federalist": BiasLabel.RIGHT,
}


def outlet_bias(name: str | None) -> BiasLabel:
    if not name:
        return BiasLabel.UNKNOWN
    low = name.strip().lower().split("|")[0].strip()
    if low in _map:
        return _map[low]
    # 域名或前缀匹配
    for key, label in _map.items():
        if key in low or low in key:
            return label
    return BiasLabel.UNKNOWN


def outlet_side(name: str | None) -> str:
    return outlet_bias(name).side
