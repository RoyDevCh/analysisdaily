"""Telegram 分发（可选）。配置 TELEGRAM_BOT_TOKEN / CHAT_ID 后启用。"""
from __future__ import annotations

import json
import urllib.request

from ..config import Settings


def send_telegram(settings: Settings, text: str) -> bool:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = json.dumps({"chat_id": settings.telegram_chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()
    return True
