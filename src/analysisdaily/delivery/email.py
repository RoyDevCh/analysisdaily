"""邮件分发（可选）。配置 SMTP_* 后启用；否则为 no-op 桩。"""
from __future__ import annotations

from ..config import Settings


def send_email(settings: Settings, subject: str, body_md: str) -> bool:
    if not (settings.smtp_host and settings.smtp_to):
        return False
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_username
    msg["To"] = settings.smtp_to
    msg.attach(MIMEText(body_md, "plain", "utf-8"))
    with smtplib.SMTP(settings.smtp_host, int(settings.smtp_port or 25)) as s:
        if settings.smtp_username:
            s.login(settings.smtp_username, settings.smtp_password)
        s.send_message(msg)
    return True
