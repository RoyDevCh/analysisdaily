"""分发编排：把"一份日报"通过已配置渠道分发到各终端。未配置自动跳过。"""
from __future__ import annotations

import logging

from ..config import Settings
from ..synthesis.daily import DailyReport
from .email import send_email
from .notion import push_rich_page
from .telegram import send_telegram

logger = logging.getLogger("analysisdaily")


def dispatch(daily: DailyReport, brief_md: str, settings: Settings) -> dict[str, bool]:
    """返回各渠道是否已发送。Notion 只推**一个**日报页（而非逐条事件）。"""
    result: dict[str, bool] = {"email": False, "telegram": False, "notion": False}
    title = f"中立客观日报 · {daily.date.isoformat()}"

    # 邮件
    try:
        result["email"] = send_email(settings, title, brief_md)
    except Exception:
        logger.warning("email dispatch failed", exc_info=True)

    # Telegram（限制 4096 字符）
    try:
        result["telegram"] = send_telegram(settings, brief_md[:4000])
    except Exception:
        logger.warning("telegram dispatch failed", exc_info=True)

    # Notion：一个页面（标题 + 综述 + 各主题 + 盲区）
    if settings.notion_token:
        try:
            blocks: list[tuple[str, str]] = [("paragraph", daily.lead_paragraph)]
            for sec in daily.sections:
                blocks.append(("heading_2", f"{sec.category}（{len(sec.items)}）"))
                for it in sec.items:
                    line = f"{it.headline}（{it.source_count} 来源）"
                    if it.key_fact:
                        line += " — " + it.key_fact
                    if it.single_source:
                        line += " [单方]"
                    blocks.append(("bulleted_list_item", line))
            if daily.reporting_gaps:
                blocks.append(("heading_2", "报道盲区"))
                for g in daily.reporting_gaps:
                    blocks.append(("bulleted_list_item", g))
            result["notion"] = push_rich_page(settings, title, blocks)
        except Exception:
            logger.warning("notion dispatch failed", exc_info=True)

    return result
