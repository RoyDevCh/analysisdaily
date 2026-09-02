"""Notion 分发（可选）。配置 NOTION_TOKEN / NOTION_DATABASE_ID 后启用。"""
from __future__ import annotations

import json
import urllib.request

from ..config import Settings

_NOTION_VERSION = "2022-06-28"


def _post(settings: Settings, url: str, payload: dict) -> int:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + settings.notion_token,
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status


def _text_block(content: str, kind: str = "paragraph") -> dict:
    return {
        "object": "block",
        "type": kind,
        kind: {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]},
    }


def push_report(settings: Settings, headline: str, body_blocks: list[str]) -> bool:
    """把一条日报写入 Notion。优先写 database；未配置 database 时回退到 page_id。"""
    if not settings.notion_token:
        return False
    body_blocks = body_blocks or []
    children = [_text_block(headline, "heading_2")] + [_text_block(b) for b in body_blocks]
    if settings.notion_database_id:
        payload = {
            "parent": {"database_id": settings.notion_database_id},
            "properties": {"Name": {"title": [{"text": {"content": headline[:180]}}]}},
            "children": children[:100],
        }
    elif settings.notion_page_id:
        payload = {"parent": {"page_id": settings.notion_page_id}, "children": children[:100]}
    else:
        return False
    _post(settings, "https://api.notion.com/v1/pages", payload)
    return True