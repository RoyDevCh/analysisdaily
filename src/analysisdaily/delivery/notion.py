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


def _block(kind: str, content: str) -> dict:
    return {
        "object": "block",
        "type": kind,
        kind: {"rich_text": [{"type": "text", "text": {"content": content[:2000]}}]},
    }


def md_to_children(markdown: str) -> list[tuple[str, str]]:
    """Markdown -> Notion children blocks（标题/段落/列表）。"""
    blocks: list[tuple[str, str]] = []
    for line in markdown.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            blocks.append(("heading_3", line[4:]))
        elif line.startswith("## "):
            blocks.append(("heading_2", line[3:]))
        elif line.startswith("# "):
            blocks.append(("heading_1", line[2:]))
        elif line.startswith("- "):
            blocks.append(("bulleted_list_item", line[2:]))
        elif line.startswith("> "):
            blocks.append(("quote", line[2:]))
        else:
            blocks.append(("paragraph", line))
    return blocks[:100]


def push_rich_page(settings: Settings, title: str, blocks: list[tuple[str, str]]) -> bool:
    """把一篇日报作为**一个** Notion 页面写入 database（或回退到 page_id）。"""
    if not settings.notion_token:
        return False
    children = [_block(kind, txt) for kind, txt in blocks][:100]
    if not children:
        return False
    if settings.notion_database_id:
        payload = {
            "parent": {"database_id": settings.notion_database_id},
            "properties": {"Name": {"title": [{"text": {"content": title[:180]}}]}},
            "children": children,
        }
    elif settings.notion_page_id:
        payload = {"parent": {"page_id": settings.notion_page_id}, "children": children}
    else:
        return False
    _post(settings, "https://api.notion.com/v1/pages", payload)
    return True