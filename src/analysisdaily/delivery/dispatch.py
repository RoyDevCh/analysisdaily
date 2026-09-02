"""分发编排：把"一份日报"通过已配置渠道分发到各终端。未配置自动跳过。"""
from __future__ import annotations

import logging

from ..config import Settings
from ..synthesis.daily import DailyReport
from .email import send_email
from .notion import md_to_children, push_rich_page
from .telegram import send_telegram

logger = logging.getLogger("analysisdaily")


def dispatch(daily: DailyReport, brief_en: str, brief_zh: str, settings: Settings) -> dict[str, bool]:
    """返回各渠道是否已发送。Notion 推**中文版 + 英文版**两页。"""
    result: dict[str, bool] = {"email": False, "telegram": False, "notion_zh": False, "notion_en": False}
    zh_title = f"中立客观日报 · {daily.date.isoformat()}（中文）"
    en_title = f"Neutral Daily Report · {daily.date.isoformat()}"

    # 邮件
    try:
        result["email"] = send_email(settings, zh_title, brief_zh)
    except Exception:
        logger.warning("email dispatch failed", exc_info=True)

    # Telegram（限制 4096 字符）
    try:
        result["telegram"] = send_telegram(settings, brief_zh[:4000])
    except Exception:
        logger.warning("telegram dispatch failed", exc_info=True)

    # Notion：中文版 + 英文版 两页（由 md_to_children 解析）
    if settings.notion_token:
        try:
            result["notion_zh"] = push_rich_page(settings, zh_title, md_to_children(brief_zh))
        except Exception:
            logger.warning("notion zh dispatch failed", exc_info=True)
        try:
            result["notion_en"] = push_rich_page(settings, en_title, md_to_children(brief_en))
        except Exception:
            logger.warning("notion en dispatch failed", exc_info=True)
    return result