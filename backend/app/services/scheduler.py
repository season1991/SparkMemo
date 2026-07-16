# APScheduler 定时任务 - 每日 00:00 标记逾期任务为 overdue_done
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text


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