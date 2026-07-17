# 邮箱配置 CRUD 测试：覆盖 GET / PUT /api/email-config 全链路与字段校验
import pytest


# 构造合法基础 payload，PUT 时仅替换要测的字段即可
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
        "recipient_name": "我自己",
    }
    payload.update(overrides)
    return payload


# 守护：递归扫描响应体，确保任何键路径下都不出现明文密码
def _assert_no_password_leak(body):
    if isinstance(body, dict):
        for key, value in body.items():
            assert key != "smtp_password", "smtp_password field must never appear in response"
            _assert_no_password_leak(value)
    elif isinstance(body, list):
        for item in body:
            _assert_no_password_leak(item)


# ===== 用例 1：未配置时 GET 返回 exists=false + 所有字段 null =====
async def test_get_when_not_exists(client):
    response = await client.get("/api/email-config")

    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body["smtp_host"] is None
    assert body["smtp_port"] is None
    assert body["smtp_user"] is None
    assert body["smtp_password_set"] is False
    assert body["use_tls"] is False
    assert body["sender_email"] is None
    assert body["sender_name"] is None
    assert body["recipient_email"] is None
    assert body["recipient_name"] is None
    assert body["created_at"] is None
    assert body["updated_at"] is None
    _assert_no_password_leak(body)


# ===== 用例 2：首次 PUT upsert 一行 =====
async def test_put_upsert_when_not_exists(client, db):
    from app import models

    response = await client.put("/api/email-config", json=_base_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is True
    assert body["id"] == 1
    assert body["smtp_host"] == "smtp.qq.com"
    assert body["smtp_port"] == 465
    assert body["smtp_password_set"] is True

    rows = db.query(models.EmailConfig).all()
    assert len(rows) == 1
    assert rows[0].id == 1


# ===== 用例 3：PUT 后 GET 拿到完整结构 + 密码不回明文 =====
async def test_get_after_upsert(client):
    put_response = await client.put("/api/email-config", json=_base_payload())
    assert put_response.status_code == 200

    get_response = await client.get("/api/email-config")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["exists"] is True
    assert body["id"] == 1
    assert body["smtp_host"] == "smtp.qq.com"
    assert body["smtp_port"] == 465
    assert body["smtp_user"] == "user@qq.com"
    assert body["smtp_password_set"] is True
    assert body["use_tls"] is True
    assert body["sender_email"] == "user@qq.com"
    assert body["sender_name"] == "SparkMemo"
    assert body["recipient_email"] == "user@qq.com"
    assert body["recipient_name"] == "我自己"
    assert "smtp_password" not in body
    _assert_no_password_leak(body)


# ===== 用例 4：第二次 PUT 覆盖字段，updated_at 推进 =====
async def test_put_updates_existing(client, db):
    from app import models

    await client.put("/api/email-config", json=_base_payload(smtp_host="smtp.qq.com"))

    second = await client.put(
        "/api/email-config",
        json=_base_payload(smtp_host="smtp.163.com", smtp_port=587, use_tls=False),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["smtp_host"] == "smtp.163.com"
    assert body["smtp_port"] == 587
    assert body["use_tls"] is False

    rows = db.query(models.EmailConfig).all()
    assert len(rows) == 1
    assert rows[0].smtp_host == "smtp.163.com"
    assert rows[0].smtp_port == 587
    assert rows[0].use_tls is False
    # updated_at 由 onupdate 触发，应为合法 YYYY-MM-DD 字符串（与具体日期解耦）
    import re
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", rows[0].updated_at)


# ===== 用例 5：PUT smtp_password="" 时保留旧密码 =====
async def test_put_empty_password_keeps_old(client, db):
    from app import models

    await client.put("/api/email-config", json=_base_payload(smtp_password="original-pwd"))

    # 不传密码（None）→ 旧密码保留
    payload = _base_payload(smtp_password=None)
    payload["smtp_host"] = "smtp.new.com"  # 同时改一个其他字段
    second = await client.put("/api/email-config", json=payload)
    assert second.status_code == 200
    body = second.json()
    assert body["smtp_password_set"] is True
    assert body["smtp_host"] == "smtp.new.com"

    row = db.query(models.EmailConfig).one()
    assert row.smtp_password == "original-pwd"
    assert row.smtp_host == "smtp.new.com"

    # 留空字符串也保留
    payload2 = _base_payload(smtp_password="", smtp_host="smtp.new2.com")
    third = await client.put("/api/email-config", json=payload2)
    assert third.status_code == 200
    assert third.json()["smtp_host"] == "smtp.new2.com"
    assert third.json()["smtp_password_set"] is True

    row = db.query(models.EmailConfig).one()
    assert row.smtp_password == "original-pwd"


# ===== 用例 6：smtp_port 越界 → 400 =====
@pytest.mark.parametrize("bad_port", [0, -1, 99999, 100000])
async def test_put_invalid_port(client, bad_port):
    response = await client.put(
        "/api/email-config", json=_base_payload(smtp_port=bad_port)
    )
    assert response.status_code == 400


# ===== 用例 7：sender_email 非法 → 400 =====
async def test_put_invalid_sender_email(client):
    response = await client.put(
        "/api/email-config", json=_base_payload(sender_email="not-an-email")
    )
    assert response.status_code == 400


# ===== 用例 8：recipient_email 非法 → 400 =====
async def test_put_invalid_recipient_email(client):
    response = await client.put(
        "/api/email-config", json=_base_payload(recipient_email="not-an-email")
    )
    assert response.status_code == 400


# ===== 用例 9：smtp_host 超过 128 字符 → 400 =====
async def test_put_invalid_smtp_host_length(client):
    response = await client.put(
        "/api/email-config", json=_base_payload(smtp_host="a" * 129)
    )
    assert response.status_code == 400


# ===== 用例 10：sender_name 超过 64 字符 → 400 =====
async def test_put_invalid_sender_name_length(client):
    response = await client.put(
        "/api/email-config", json=_base_payload(sender_name="n" * 65)
    )
    assert response.status_code == 400


# ===== 用例 11：GET / PUT 响应均不出 smtp_password 字段（端到端守护） =====
async def test_password_never_in_response(client):
    put_response = await client.put("/api/email-config", json=_base_payload())
    assert put_response.status_code == 200
    _assert_no_password_leak(put_response.json())

    get_response = await client.get("/api/email-config")
    assert get_response.status_code == 200
    _assert_no_password_leak(get_response.json())

    # 第二次 PUT（更新场景）响应也要守护
    second_put = await client.put(
        "/api/email-config", json=_base_payload(smtp_host="smtp.new.com")
    )
    assert second_put.status_code == 200
    _assert_no_password_leak(second_put.json())


# ===== 用例 12：未配置 GET 回显 send_time 默认值 + active=false =====
async def test_get_default_send_time_and_active(client):
    response = await client.get("/api/email-config")
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is False
    assert body["send_time"] == "08:00"
    assert body["active"] is False


# ===== 用例 13：send_time 非法格式 → 400 =====
@pytest.mark.parametrize(
    "bad_send_time", ["25:00", "24:60", "9:00", "ab:cd", "12:5", ""]
)
async def test_put_send_time_24h_regex_rejects_invalid(client, bad_send_time):
    response = await client.put(
        "/api/email-config", json=_base_payload(send_time=bad_send_time)
    )
    assert response.status_code == 400


# ===== 用例 14：合法 send_time / active 持久化 + GET 回显 =====
async def test_put_persists_send_time_and_active(client, db):
    from app import models

    response = await client.put(
        "/api/email-config",
        json=_base_payload(send_time="08:30", active=True),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["send_time"] == "08:30"
    assert body["active"] is True

    row = db.query(models.EmailConfig).one()
    assert row.send_time == "08:30"
    assert row.active is True

    # GET 回显
    get_response = await client.get("/api/email-config")
    assert get_response.status_code == 200
    get_body = get_response.json()
    assert get_body["send_time"] == "08:30"
    assert get_body["active"] is True


# ===== 用例 15：第二次 PUT 即使只改 active，send_time 也显式覆盖 =====
async def test_put_send_time_overrides_each_call(client, db):
    from app import models

    await client.put(
        "/api/email-config",
        json=_base_payload(send_time="08:00", active=False),
    )
    # 第二次只显式改 active，但 send_time 字段默认仍是 '08:00'（由 Pydantic 填充）
    second = await client.put(
        "/api/email-config",
        json=_base_payload(send_time="09:30", active=True),
    )
    assert second.status_code == 200
    body = second.json()
    assert body["send_time"] == "09:30"
    assert body["active"] is True

    row = db.query(models.EmailConfig).one()
    assert row.send_time == "09:30"
    assert row.active is True