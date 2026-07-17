# 邮件发送封装：基于 stdlib smtplib，支持 465 SSL / 587 STARTTLS / 25 明文三种 transport。
from __future__ import annotations

import smtplib
import socket
from email.mime.text import MIMEText
from email.utils import formataddr

from app import models


class MailerError(Exception):
    """邮件发送失败统一异常（连接 / 认证 / 超时 / 其它 SMTP 异常）。"""


def _build_message(
    config: models.EmailConfig, subject: str, html_body: str
) -> MIMEText:
    """构造 MIMEText 邮件，From = sender_email / sender_name；To = recipient_email。"""
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((config.sender_name, config.sender_email))
    msg["To"] = formataddr((config.recipient_name or "", config.recipient_email))
    return msg


def _connect(config: models.EmailConfig) -> smtplib.SMTP:
    """按 use_tls / port 选择 transport，返回已就绪的 SMTP 客户端。

    - use_tls=True & port=465 → SMTP_SSL（直接 TLS 握手）
    - use_tls=True & port=587 → SMTP + starttls()
    - use_tls=False           → SMTP 明文
    """
    timeout = 10
    if config.use_tls and config.smtp_port == 465:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            config.smtp_host, config.smtp_port, timeout=timeout
        )
    else:
        client = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=timeout)
        if config.use_tls:
            # 587 STARTTLS 路径：明文连上后升级
            client.starttls()
    return client


def send_html(config: models.EmailConfig, subject: str, html_body: str) -> None:
    """发送 HTML 邮件到 config.recipient_email。

    异常:
        MailerError: 连接 / 认证 / 超时 / 其它 SMTP 失败。
    """
    msg = _build_message(config, subject, html_body)
    try:
        client = _connect(config)
    except (socket.timeout, OSError) as exc:
        raise MailerError(f"smtp connect failed: {exc}") from exc

    try:
        try:
            client.login(config.smtp_user, config.smtp_password)
        except (smtplib.SMTPAuthenticationError, smtplib.SMTPException) as exc:
            raise MailerError(f"smtp login failed: {exc}") from exc

        try:
            client.send_message(msg)
        except (smtplib.SMTPException, socket.timeout, OSError) as exc:
            raise MailerError(f"smtp send failed: {exc}") from exc
    finally:
        try:
            client.quit()
        except (smtplib.SMTPException, OSError):
            # quit 失败不掩盖上面的错误；连接可能已被远端关闭
            pass