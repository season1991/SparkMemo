# POST /api/email/send-test 测试：先 upsert 入参配置，再发测试邮件
import re
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app import models


def _base_payload(**overrides):
    payload = {
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "smtp_user": "user@qq.com",
        "smtp_password": "secret-token-123",
        "use_tls": True,
        "sender_email": "user@qq.com",
        "sender_name": "SparkMemo",
        "recipient_email": "user@qq.com",
        "recipient_name": None,
        "send_time": "08:00",
        "active": False,
    }
    payload.update(overrides)
    return payload


# ===== 用例 1：send_time 非法 → 422（/api/email/send-test 不在 /api/email-config 前缀下） =====
async def test_send_test_invalid_field_returns_422(client):
    response = await client.post(
        "/api/email/send-test", json=_base_payload(send_time="25:00")
    )
    assert response.status_code == 422


# ===== 用例 2：mock SMTP 抛错 → 500 + detail =====
async def test_send_test_smtp_failure_returns_500(client):
    import smtplib

    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_ssl:
        client_smtp = MagicMock()
        client_smtp.send_message.side_effect = smtplib.SMTPException("auth failed")
        mock_ssl.return_value = client_smtp

        response = await client.post(
            "/api/email/send-test", json=_base_payload()
        )
        assert response.status_code == 500
        body = response.json()
        assert "smtp send failed" in body["detail"]


# ===== 用例 3：成功 → 200 + {ok, sent_at, recipient} =====
async def test_send_test_success_response(client):
    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_ssl:
        client_smtp = MagicMock()
        mock_ssl.return_value = client_smtp

        response = await client.post(
            "/api/email/send-test",
            json=_base_payload(recipient_email="recv@qq.com"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["recipient"] == "recv@qq.com"
        # sent_at 形如 2026-08-10T12:34:56.789012+00:00
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", body["sent_at"])
        client_smtp.send_message.assert_called_once()


# ===== 用例 4：send-test 先持久化入参配置 =====
async def test_send_test_persists_config_before_send(client, db):
    with patch("app.services.mailer.smtplib.SMTP_SSL") as mock_ssl:
        client_smtp = MagicMock()
        mock_ssl.return_value = client_smtp

        response = await client.post(
            "/api/email/send-test",
            json=_base_payload(
                smtp_host="smtp.test.com",
                sender_name="TestSender",
                active=True,
                send_time="10:30",
            ),
        )
        assert response.status_code == 200

        row = db.query(models.EmailConfig).one()
        assert row.smtp_host == "smtp.test.com"
        assert row.sender_name == "TestSender"
        assert row.active is True
        assert row.send_time == "10:30"
        # 密码已落库（明文，与既有约定一致）
        assert row.smtp_password == "secret-token-123"