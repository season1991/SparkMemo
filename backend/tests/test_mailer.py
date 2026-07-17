# mailer 测试：mock smtplib，覆盖三段式 transport + 失败路径 + 消息头
import smtplib
import socket
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

import pytest

from app import models
from app.services.mailer import MailerError, send_html


def _make_config(**overrides):
    """构造 EmailConfig ORM 风格对象（MagicMock 模拟字段访问）。"""
    cfg = models.EmailConfig(
        id=1,
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_user="user@qq.com",
        smtp_password="secret",
        use_tls=True,
        sender_email="user@qq.com",
        sender_name="SparkMemo",
        recipient_email="recv@qq.com",
        recipient_name="我自己",
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ===== 用例 1：use_tls=True & port=465 → SMTP_SSL =====
def test_send_html_uses_smtp_ssl_for_465():
    cfg = _make_config(use_tls=True, smtp_port=465)
    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_ssl, \
         patch("app.services.mailer.smtplib.SMTP") as mock_plain:
        client = MagicMock()
        mock_ssl.return_value = client

        send_html(cfg, "Subject", "<p>hi</p>")

        mock_ssl.assert_called_once_with("smtp.qq.com", 465, timeout=10)
        mock_plain.assert_not_called()
        client.login.assert_called_once_with("user@qq.com", "secret")
        client.send_message.assert_called_once()
        client.quit.assert_called_once()


# ===== 用例 2：use_tls=True & port=587 → SMTP + starttls =====
def test_send_html_uses_starttls_for_587():
    cfg = _make_config(use_tls=True, smtp_port=587)
    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_ssl, \
         patch("app.services.mailer.smtplib.SMTP") as mock_plain:
        client = MagicMock()
        mock_plain.return_value = client

        send_html(cfg, "Subject", "<p>hi</p>")

        mock_plain.assert_called_once_with("smtp.qq.com", 587, timeout=10)
        mock_ssl.assert_not_called()
        client.starttls.assert_called_once()
        client.login.assert_called_once()
        client.send_message.assert_called_once()


# ===== 用例 3：use_tls=False & port=25 → 明文 SMTP，不调 starttls =====
def test_send_html_uses_plain_for_25():
    cfg = _make_config(use_tls=False, smtp_port=25)
    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_ssl, \
         patch("app.services.mailer.smtplib.SMTP") as mock_plain:
        client = MagicMock()
        mock_plain.return_value = client

        send_html(cfg, "Subject", "<p>hi</p>")

        mock_plain.assert_called_once_with("smtp.qq.com", 25, timeout=10)
        mock_ssl.assert_not_called()
        client.starttls.assert_not_called()
        client.login.assert_called_once()
        client.send_message.assert_called_once()


# ===== 用例 4：SMTPException → MailerError =====
def test_send_html_raises_mailer_error_on_smtp_exception():
    cfg = _make_config(use_tls=False, smtp_port=25)
    with patch("app.services.mailer.smtplib.SMTP") as mock_plain:
        client = MagicMock()
        client.send_message.side_effect = smtplib.SMTPException("boom")
        mock_plain.return_value = client

        with pytest.raises(MailerError) as exc_info:
            send_html(cfg, "Subject", "<p>hi</p>")
        assert "smtp send failed" in str(exc_info.value)


# ===== 用例 5：socket.timeout → MailerError =====
def test_send_html_raises_mailer_error_on_timeout():
    cfg = _make_config(use_tls=False, smtp_port=25)
    with patch("app.services.mailer.smtplib.SMTP") as mock_plain:
        mock_plain.side_effect = socket.timeout("timed out")

        with pytest.raises(MailerError) as exc_info:
            send_html(cfg, "Subject", "<p>hi</p>")
        assert "smtp connect failed" in str(exc_info.value)


# ===== 用例 6：消息头正确（Subject / From / To） =====
def test_send_html_message_headers():
    cfg = _make_config(
        sender_email="from@qq.com",
        sender_name="FromName",
        recipient_email="to@qq.com",
        recipient_name="ToName",
    )
    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_ssl:
        client = MagicMock()
        mock_ssl.return_value = client

        send_html(cfg, "My Subject", "<p>hello</p>")

        sent_msg = client.send_message.call_args[0][0]
        assert isinstance(sent_msg, MIMEText)
        assert sent_msg["Subject"] == "My Subject"
        # formataddr 输出可能为 "FromName <from@qq.com>"，做包含判断
        assert "from@qq.com" in sent_msg["From"]
        assert "to@qq.com" in sent_msg["To"]