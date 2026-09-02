"""样本夹具加载：从 data/e2e_sample/*.json 读取 RawArticle，用于离线可复现的演示。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..models.raw import Channel, RawArticle
from ..models.report import BiasLabel


def load_fixture_dir(base: Path) -> list[RawArticle]:
    """读取 fixtures 目录。每个 json 文件是一个对象或文章数组。

    支持字段：source_name, channel, bias, side, title, url, published(ISO), summary, content。
    """
    out: list[RawArticle] = []
    for path in sorted(base.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else [data]
        for it in items:
            out.append(_to_article(it, path))
    return out


def _to_article(d: dict, path: Path) -> RawArticle:
    bias = BiasLabel(d.get("bias", "Center")) if d.get("bias") else BiasLabel.UNKNOWN
    channel = Channel(d.get("channel", "wire"))
    published = d.get("published")
    if isinstance(published, str):
        published = datetime.fromisoformat(published.replace("Z", "+00:00"))
    return RawArticle(
        id=d.get("id") or f"fixture-{path.stem}-{hash(d.get('title',''))&0xffffffff:08x}",
        source_name=d.get("source_name", path.stem),
        channel=channel,
        bias=bias,
        side=bias.side,
        title=d.get("title", ""),
        url=d.get("url", ""),
        published=published or datetime.now(timezone.utc),
        summary=d.get("summary", ""),
        content=d.get("content", d.get("summary", "")),
    )
