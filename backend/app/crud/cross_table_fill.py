"""跨表数据填充 CRUD 层（v0.6.0）。

封装 `cross_table_fill_jobs` / `cross_table_fill_rows` / `cross_table_fill_configs` 三张表的最小操作集：
- create_job / get_job / list_jobs / delete_job
- bulk_insert_rows / get_rows / update_row_key_value
- upsert_config
- token store：进程内 dict，5min TTL

不抛 HTTPException；调用方负责按场景映射为 4xx。
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import models


# ====================== Job ======================


def _today_str() -> str:
    """返回当前日期的 YYYY-MM-DD 字符串。供 created_at / updated_at / expires_at 使用。"""
    return date.today().isoformat()


def create_job(
    db,
    *,
    target_filename: str,
    base_filename: str,
    target_headers: list[str],
    base_headers: list[str],
    target_row_count: int,
    base_row_count: int,
    expires_in_hours: int = 24,
) -> models.CrossTableFillJob:
    """创建任务元数据行（cross_table_fill_jobs 表）。

    参数:
        db: SQLAlchemy Session。
        target_filename: 原 target xlsx 文件名（含扩展名）。
        base_filename: 原 base xlsx 文件名。
        target_headers: target 表头列表。
        base_headers: base 表头列表。
        target_row_count: target 数据行数。
        base_row_count: base 数据行数。
        expires_in_hours: 过期小时数（1-168，默认 24）。

    返回:
        models.CrossTableFillJob: 已写入并 refresh 的行实例（含自增 id）。
    """
    today = _today_str()
    expires_at = (date.today() + timedelta(hours=expires_in_hours)).isoformat()
    job = models.CrossTableFillJob(
        target_filename=target_filename,
        base_filename=base_filename,
        target_headers=json.dumps(target_headers, ensure_ascii=False),
        base_headers=json.dumps(base_headers, ensure_ascii=False),
        target_row_count=target_row_count,
        base_row_count=base_row_count,
        status="pending",
        created_at=today,
        updated_at=today,
        expires_at=expires_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db, job_id: int) -> Optional[models.CrossTableFillJob]:
    """按主键查 job；不存在返回 None。"""
    return db.get(models.CrossTableFillJob, job_id)


def list_jobs(
    db,
    *,
    page: int = 1,
    size: int = 20,
    status: Optional[str] = None,
) -> tuple[list[models.CrossTableFillJob], int]:
    """列表查询（id 倒序）。

    返回 (items, total)。
    """
    stmt = select(models.CrossTableFillJob).order_by(models.CrossTableFillJob.id.desc())
    count_stmt = select(func.count()).select_from(models.CrossTableFillJob)
    if status:
        stmt = stmt.where(models.CrossTableFillJob.status == status)
        count_stmt = count_stmt.where(models.CrossTableFillJob.status == status)
    items = db.execute(stmt.offset((page - 1) * size).limit(size)).scalars().all()
    total = db.execute(count_stmt).scalar_one()
    return list(items), int(total)


def delete_job(db, job_id: int) -> bool:
    """删除 job；外键 CASCADE 自动清 rows / configs。"""
    job = db.get(models.CrossTableFillJob, job_id)
    if job is None:
        return False
    db.delete(job)
    db.commit()
    return True


def update_job_status(
    db,
    job: models.CrossTableFillJob,
    *,
    status: str,
    result_row_count: Optional[int] = None,
    filled_count: Optional[int] = None,
    unmatched_count: Optional[int] = None,
    multi_match_count: Optional[int] = None,
) -> None:
    """更新 job 状态与执行结果字段。"""
    job.status = status
    if result_row_count is not None:
        job.result_row_count = result_row_count
    if filled_count is not None:
        job.filled_count = filled_count
    if unmatched_count is not None:
        job.unmatched_count = unmatched_count
    if multi_match_count is not None:
        job.multi_match_count = multi_match_count
    job.updated_at = _today_str()
    db.commit()


def is_job_expired(job: models.CrossTableFillJob) -> bool:
    """判断 job 是否过期（expires_at < today）。"""
    return job.expires_at < _today_str()


# ====================== Rows ======================


def bulk_insert_rows(
    db,
    *,
    job_id: int,
    role: str,
    rows: list[dict],
) -> None:
    """批量插入 cross_table_fill_rows。

    参数:
        db: SQLAlchemy Session。
        job_id: 关联 job_id。
        role: 'target' / 'base'。
        rows: 每项是 dict，key 为字段名。
    """
    if not rows:
        return
    objs = [
        models.CrossTableFillRow(
            job_id=job_id,
            role=role,
            row_index=i,
            key_value=None,
            data=json.dumps(r, ensure_ascii=False, default=_json_default),
        )
        for i, r in enumerate(rows)
    ]
    db.add_all(objs)
    db.commit()


def _json_default(obj: Any) -> Any:
    """JSON 序列化兜底：datetime / Decimal 等转 str。"""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def get_rows_by_role(
    db,
    *,
    job_id: int,
    role: str,
) -> list[dict]:
    """按 job_id + role 查所有行；返回 list[dict]。"""
    rows = db.execute(
        select(models.CrossTableFillRow)
        .where(
            models.CrossTableFillRow.job_id == job_id,
            models.CrossTableFillRow.role == role,
        )
        .order_by(models.CrossTableFillRow.row_index.asc())
    ).scalars().all()
    return [json.loads(r.data) for r in rows]


def update_row_key_value(db, *, job_id: int, role: str, row_index: int, key_value: Optional[str]) -> None:
    """更新指定行的 key_value（执行阶段回写主键归一化值）。"""
    db.execute(
        models.CrossTableFillRow.__table__.update()
        .where(
            models.CrossTableFillRow.job_id == job_id,
            models.CrossTableFillRow.role == role,
            models.CrossTableFillRow.row_index == row_index,
        )
        .values(key_value=key_value)
    )
    db.commit()


# ====================== Configs ======================


def upsert_config(
    db,
    *,
    job_id: int,
    target_keys: list[str],
    base_keys: list[str],
    mappings: list[dict],
    join_mode: str,
    match_mode: str,
    case_sensitive: bool,
    trim_strings: bool,
    confirm_token: Optional[str],
) -> models.CrossTableFillConfig:
    """创建或更新 job 的匹配配置（job_id PK，故即「替换」）。"""
    today = _today_str()
    config = db.get(models.CrossTableFillConfig, job_id)
    if config is None:
        config = models.CrossTableFillConfig(
            job_id=job_id,
            target_keys=json.dumps(target_keys, ensure_ascii=False),
            base_keys=json.dumps(base_keys, ensure_ascii=False),
            mappings=json.dumps(mappings, ensure_ascii=False),
            join_mode=join_mode,
            match_mode=match_mode,
            case_sensitive=case_sensitive,
            trim_strings=trim_strings,
            confirm_token=confirm_token,
            created_at=today,
            updated_at=today,
        )
        db.add(config)
    else:
        config.target_keys = json.dumps(target_keys, ensure_ascii=False)
        config.base_keys = json.dumps(base_keys, ensure_ascii=False)
        config.mappings = json.dumps(mappings, ensure_ascii=False)
        config.join_mode = join_mode
        config.match_mode = match_mode
        config.case_sensitive = case_sensitive
        config.trim_strings = trim_strings
        config.confirm_token = confirm_token
        config.updated_at = today
    db.commit()
    db.refresh(config)
    return config


def get_config(db, job_id: int) -> Optional[models.CrossTableFillConfig]:
    """按 job_id 查 config。"""
    return db.get(models.CrossTableFillConfig, job_id)


# ====================== Token Store ======================
# 进程内 dict；server 重启后会丢失。短期下载足够。


_DOWNLOAD_TTL_SEC = 300  # 5 minutes
_TOKEN_STORE: dict[str, tuple[int, str]] = {}  # token -> (job_id, created_at_epoch)


def put_download_token(job_id: int) -> str:
    """生成并存储一个 download token；返回 token 字符串。"""
    token = secrets.token_urlsafe(24)
    now = int(time.time())
    _TOKEN_STORE[token] = (job_id, now)
    # 顺手清理过期
    _cleanup_expired(now)
    return token


def take_download_token(token: str) -> Optional[int]:
    """校验 token；合法返回 job_id；否则 None。"""
    now = int(time.time())
    entry = _TOKEN_STORE.get(token)
    if entry is None:
        return None
    job_id, created_at = entry
    if now - created_at > _DOWNLOAD_TTL_SEC:
        _TOKEN_STORE.pop(token, None)
        return None
    return job_id


def pop_download_token(token: str) -> None:
    """显式删除 token（可选，用完即丢）。"""
    _TOKEN_STORE.pop(token, None)


def _cleanup_expired(now: int) -> None:
    """清理过期 token，避免内存泄漏。"""
    expired = [t for t, (_, ts) in _TOKEN_STORE.items() if now - ts > _DOWNLOAD_TTL_SEC]
    for t in expired:
        _TOKEN_STORE.pop(t, None)
