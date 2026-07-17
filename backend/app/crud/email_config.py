# 邮箱配置 CRUD 操作：单行表，按 id=1 读写
from typing import Optional

from app import models
from app.schemas import EmailConfigWrite


def get_email_config(db) -> Optional[models.EmailConfig]:
    """按 id=1 查单行；不存在返回 None。"""
    return db.get(models.EmailConfig, 1)


def upsert_email_config(db, payload: EmailConfigWrite) -> models.EmailConfig:
    """单行 upsert。

    行为:
        - 若不存在 -> INSERT 一行（id=1）
        - 若存在且 smtp_password 为空/None -> 保留旧密码，其他字段 UPDATE
        - 若存在且 smtp_password 非空 -> 覆盖密码，其他字段 UPDATE
        - send_time / active 每次 PUT 显式覆盖（与 smtp_password 行为不同）

    返回:
        EmailConfig: 持久化后的对象
    """
    existing = db.get(models.EmailConfig, 1)
    if existing is None:
        # INSERT 路径：smtp_password 必填（schema 校验已通过）
        row = models.EmailConfig(
            id=1,
            smtp_host=payload.smtp_host,
            smtp_port=payload.smtp_port,
            smtp_user=payload.smtp_user,
            smtp_password=payload.smtp_password or "",
            use_tls=payload.use_tls,
            sender_email=payload.sender_email,
            sender_name=payload.sender_name,
            recipient_email=payload.recipient_email,
            recipient_name=payload.recipient_name,
            send_time=payload.send_time,
            active=payload.active,
        )
        db.add(row)
    else:
        existing.smtp_host = payload.smtp_host
        existing.smtp_port = payload.smtp_port
        existing.smtp_user = payload.smtp_user
        # 密码：留空 / None -> 保留旧值；非空 -> 覆盖
        if payload.smtp_password:
            existing.smtp_password = payload.smtp_password
        existing.use_tls = payload.use_tls
        existing.sender_email = payload.sender_email
        existing.sender_name = payload.sender_name
        existing.recipient_email = payload.recipient_email
        existing.recipient_name = payload.recipient_name
        # 调度字段：每次 PUT 显式覆盖（不留空保留）
        existing.send_time = payload.send_time
        existing.active = payload.active
        # updated_at 由 onupdate=_today_str 自动更新
        db.add(existing)
    db.commit()
    result = existing if existing is not None else row
    db.refresh(result)

    # 提交后同步 APScheduler Job（active=true → 重设；active=false → 暂停）
    try:
        from app.services.scheduler import sync_email_dispatch_job

        sync_email_dispatch_job(result)
    except Exception:
        # 调度器同步失败不影响配置写入；日志留待 mail_logs 上线后处理
        pass

    return result