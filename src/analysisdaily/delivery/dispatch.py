"""分发编排：把当天日报通过已配置的渠道分发。未配置的渠道自动跳过。"""
from __future__ import annotations

import logging

from ..config import Settings
from ..models.report import StructuredReport
from .email import send_email
from .notion import push_report
from .telegram import send_telegram

logger = logging.getLogger("analysisdaily")


def dispatch(reports: list[StructuredReport], daily_md: str, settings: Settings) -> dict[str, bool]:
    """返回各渠道是否已发送。"""
    result: dict[str, bool] = {"email": False, "telegram": False, "notion": False}
    date_str = reports[0].date.isoformat() if reports else ""

    # 邮件
    subject = f"中立客观日报 · {date_str}"
    try:
        result["email"] = send_email(settings, subject, daily_md)
    except Exception:
        logger.warning("email dispatch failed", exc_info=True)

    # Telegram（限制 4096 字符）
    try:
        result["telegram"] = send_telegram(settings, daily_md[:4000])
    except Exception:
        logger.warning("telegram dispatch failed", exc_info=True)

    # Notion：每条日报一页
    for r in reports:
        try:
            body = [
                f"类别: {r.category}",
                f"事件ID: {r.event_id}",
                "核验事实:",
            ]
            for f in r.verified_facts:
                body.append(f"  - {f.text} ({f.quote_spans[0].source_name})")
            body.append(f"左翼侧重: {r.perspectives_divergence.left_leaning_focus}")
            body.append(f"右翼侧重: {r.perspectives_divergence.right_leaning_focus}")
            body.append(f"盲区提示: {r.perspectives_divergence.blindspot_warning}")
            if push_report(settings, r.headline, body):
                result["notion"] = True
        except Exception:
            logger.warning("notion dispatch failed for %s", r.event_id, exc_info=True)

    return result
