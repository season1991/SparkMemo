# APScheduler 定时任务 - 每日 00:00 标记逾期任务为 overdue_done
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app import models


def get_today() -> str:
    """返回今天的 YYYY-MM-DD 字符串，供 Job 和 API 层共用，支持测试 monkeypatch。"""
    return date.today().isoformat()


def check_overdue_tasks(db, today: str | None = None) -> None:
    """
    逾期自动完成任务：将 due_at 距 today 超过 3 天的 pending 任务标记为 overdue_done。

    参数:
        db: 数据库会话
        today: 可选，YYYY-MM-DD 格式；缺省时由 Python date.today().isoformat() 计算

    异常:
        无显式抛出，数据库错误由 SQLAlchemy 抛出
    """
    today_str = today or get_today()
    cutoff = (date.fromisoformat(today_str) - timedelta(days=3)).isoformat()

    overdue_ids = db.execute(
        text("SELECT id FROM tasks WHERE status = 'pending' AND due_at <= :cutoff"),
        {"cutoff": cutoff},
    ).fetchall()

    for row in overdue_ids:
        db.execute(
            text(
                "UPDATE tasks SET status = 'overdue_done', "
                "completed_at = :today, updated_at = :today "
                "WHERE id = :id AND status = 'pending'"
            ),
            {"id": row[0], "today": today_str},
        )
    db.commit()


def _job_wrapper() -> None:
    """APScheduler Job 包装函数：创建独立会话后执行逾期检查。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        check_overdue_tasks(db)
    finally:
        db.close()


# ========== v0.4 每日邮件 Job ==========

EMAIL_DISPATCH_JOB_ID = "email_daily_dispatch"


def _email_dispatch_wrapper() -> None:
    """APScheduler Job 包装函数：读 email_config；active=true 才发；SMTP 失败静默吞掉。"""
    from app.database import SessionLocal
    from app.crud.email_config import get_email_config
    from app.services import email_dispatcher
    from app.services.mailer import MailerError, send_html

    db = SessionLocal()
    try:
        cfg = get_email_config(db)
        if cfg is None or not cfg.active:
            return
        today_str = get_today()
        subject, html = email_dispatcher.render_daily_dispatch(today_str, db)
        try:
            send_html(cfg, subject, html)
        except MailerError:
            # v0.4 不持久化失败日志；mail_logs 上线前静默吞掉
            pass
    finally:
        db.close()


def sync_email_dispatch_job(config: Optional[models.EmailConfig]) -> None:
    """根据 DB 里的 (active, send_time) 重设 / 暂停 Job。CRUD 提交后调用。

    行为:
        - config 为 None 或 active=False → pause_job（Job id 保留，便于后续 resume）
        - config.active=True 且 send_time 合法 → reschedule_job 替换 trigger；
          若 Job 不存在（极少见，预注册已保证 id 存在）则 add_job 兜底
    """
    job = apscheduler_instance.get_job(EMAIL_DISPATCH_JOB_ID)

    if config is None or not config.active:
        if job is not None:
            apscheduler_instance.pause_job(EMAIL_DISPATCH_JOB_ID)
        return

    hour_str, minute_str = config.send_time.split(":")
    new_trigger = CronTrigger(
        hour=int(hour_str),
        minute=int(minute_str),
        timezone="Asia/Shanghai",
    )

    if job is not None:
        # reschedule_job 真正替换 trigger；add_job(replace_existing=True) 在某些
        # APScheduler 版本下不会更新已存在 job 的 trigger。
        apscheduler_instance.reschedule_job(
            EMAIL_DISPATCH_JOB_ID,
            trigger=new_trigger,
        )
    else:
        apscheduler_instance.add_job(
            _email_dispatch_wrapper,
            trigger=new_trigger,
            id=EMAIL_DISPATCH_JOB_ID,
            replace_existing=False,
            coalesce=True,
            misfire_grace_time=3600,
        )


# 创建后台调度器，注册每日 00:00 执行的逾期任务检查 Job
apscheduler_instance = BackgroundScheduler(timezone="Asia/Shanghai")
apscheduler_instance.add_job(
    _job_wrapper,
    trigger="cron",
    hour=0,
    minute=0,
    id="check_overdue_tasks",
    replace_existing=True,
)

# 预注册 email_daily_dispatch Job（paused）——保证 Job id 存在，
# 后续 sync_email_dispatch_job 可直接 add_job(replace_existing=True) 或 pause_job
apscheduler_instance.add_job(
    _email_dispatch_wrapper,
    trigger=CronTrigger(hour=8, minute=0, timezone="Asia/Shanghai"),
    id=EMAIL_DISPATCH_JOB_ID,
    replace_existing=True,
    coalesce=True,
    misfire_grace_time=3600,
)
apscheduler_instance.pause_job(EMAIL_DISPATCH_JOB_ID)