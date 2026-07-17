# scheduler.sync_email_dispatch_job 测试：active/send_time 切换触发器与 pause
from app import models
from app.services.scheduler import (
    EMAIL_DISPATCH_JOB_ID,
    apscheduler_instance,
    sync_email_dispatch_job,
)


def _make_config(active: bool, send_time: str = "08:00"):
    """构造不落库的 ORM 对象（仅用于 sync 函数入参）。"""
    return models.EmailConfig(
        id=1,
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_user="user@qq.com",
        smtp_password="x",
        use_tls=True,
        sender_email="user@qq.com",
        sender_name="SparkMemo",
        recipient_email="user@qq.com",
        recipient_name=None,
        send_time=send_time,
        active=active,
    )


# ===== 用例 1：active=true → Job 替换 trigger 至 send_time =====
def test_sync_with_active_true_reschedules_job():
    cfg = _make_config(active=True, send_time="08:30")
    try:
        sync_email_dispatch_job(cfg)
        job = apscheduler_instance.get_job(EMAIL_DISPATCH_JOB_ID)
        assert job is not None

        # 通过 get_next_fire_time 验证 trigger 实际生效：返回 datetime 在 08:30 触发
        from datetime import datetime, timedelta

        tz = apscheduler_instance.timezone
        # 用明天作为基准，避免与 now 时分秒边界撞车
        now = datetime.now(tz) + timedelta(days=1)
        next_fire = job.trigger.get_next_fire_time(None, now)
        assert next_fire is not None
        local = next_fire.astimezone(tz)
        assert local.hour == 8
        assert local.minute == 30
    finally:
        # 还原为 paused 状态，避免污染后续测试
        apscheduler_instance.pause_job(EMAIL_DISPATCH_JOB_ID)


# ===== 用例 2：active=false → Job pause =====
def test_sync_with_active_false_pauses_job():
    cfg = _make_config(active=False, send_time="08:00")
    sync_email_dispatch_job(cfg)

    job = apscheduler_instance.get_job(EMAIL_DISPATCH_JOB_ID)
    assert job is not None
    apscheduler_instance.pause_job(EMAIL_DISPATCH_JOB_ID)
    assert apscheduler_instance.get_job(EMAIL_DISPATCH_JOB_ID) is not None


# ===== 用例 3：config=None → Job pause =====
def test_sync_with_none_config_pauses_job():
    sync_email_dispatch_job(None)
    job = apscheduler_instance.get_job(EMAIL_DISPATCH_JOB_ID)
    assert job is not None
    apscheduler_instance.pause_job(EMAIL_DISPATCH_JOB_ID)