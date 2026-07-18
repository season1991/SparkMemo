"""DSP 上传 CRUD 操作（v0.5）。

封装 `dsp_uploads` / `dsp_upload_rows` 两张表的最小操作集：find_by_version / create_upload /
bulk_insert_rows / get_upload / list_uploads / list_rows / delete_upload。所有方法不抛 4xx HTTPException，
业务异常（IntegrityError 等）由调用方按场景映射为 400 / 404 / 409 / 500 等。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import models


def find_by_version(
    db,
    *,
    vendor: str,
    item: str,
    sub_item: str,
    version_date: str,
) -> Optional[models.DspUpload]:
    """按 (vendor, item, sub_item, version_date) 联合唯一键查询批次。

    参数:
        db: SQLAlchemy Session。
        vendor: 文件名第 1 段。
        item: 文件名第 2 段。
        sub_item: 文件名第 3 段。
        version_date: 10 字符 `YYYY-MM-DD`。

    返回:
        models.DspUpload 或 None：找到则返回行实例，不存在则返回 None。

    异常:
        无业务异常。
    """
    return db.execute(
        select(models.DspUpload).where(
            models.DspUpload.vendor == vendor,
            models.DspUpload.item == item,
            models.DspUpload.sub_item == sub_item,
            models.DspUpload.version_date == version_date,
        )
    ).scalar_one_or_none()


def create_upload(
    db,
    *,
    vendor: str,
    item: str,
    sub_item: str,
    version_date: str,
    source_filename: str,
    row_count: int,
    created_at: str,
) -> models.DspUpload:
    """创建批次元数据行（`dsp_uploads` 表）。

    参数:
        db: SQLAlchemy Session。
        vendor: 文件名第 1 段。
        item: 文件名第 2 段。
        sub_item: 文件名第 3 段。
        version_date: 10 字符 `YYYY-MM-DD`（用户输入）。
        source_filename: 含扩展名的原始文件名（展示 / 审计用）。
        row_count: 已展开的事实行条数（跳过 quantity 为空/0 后的有效行数）。
        created_at: 10 字符 `YYYY-MM-DD`（批次创建日，由 Python 调用方写入，不依赖 DB 函数）。

    返回:
        models.DspUpload: 已写入并 refresh 后的批次行实例（含自增 id）。

    异常:
        IntegrityError: 联合唯一键冲突（重复同版本）或数据库约束违例；调用方负责回滚并映射 409。
    """
    upload = models.DspUpload(
        vendor=vendor,
        item=item,
        sub_item=sub_item,
        version_date=version_date,
        source_filename=source_filename,
        row_count=row_count,
        created_at=created_at,
    )
    db.add(upload)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(upload)
    return upload


def bulk_insert_rows(db, upload_id: int, fact_rows: list[dict]) -> None:
    """批量插入事实行（`dsp_upload_rows` 表）。

    使用 `session.add_all` 让 SQLAlchemy 在 commit 时合成 multi-row INSERT，避免 N 次单条 INSERT。
    上千行的批次可显著降低往返成本。

    参数:
        db: SQLAlchemy Session。
        upload_id: 批次主键（外键引用 `dsp_uploads.id`）。
        fact_rows: 每项为字段名 → 值的 dict，应包含 `country / category / config_code / data_type /
            ttl / ym / week / date / quantity` 全部字段（除 `upload_id` 由本函数补）。

    返回:
        None。

    异常:
        IntegrityError: 数据库约束违例（如外键丢失）；调用方负责回滚。
    """
    if not fact_rows:
        return
    db.add_all([models.DspUploadRow(upload_id=upload_id, **fr) for fr in fact_rows])
    db.commit()


def get_upload(db, upload_id: int) -> Optional[models.DspUpload]:
    """按主键查询批次。

    参数:
        db: SQLAlchemy Session。
        upload_id: 批次主键。

    返回:
        models.DspUpload 或 None：找到则返回行实例，不存在则返回 None。

    异常:
        无业务异常。
    """
    return db.get(models.DspUpload, upload_id)


def list_uploads(db, *, page: int = 1, size: int = 20) -> tuple[list[models.DspUpload], int]:
    """批次列表（按 id 倒序），分页返回 (items, total)。

    参数:
        db: SQLAlchemy Session。
        page: 页码（从 1 开始）。
        size: 每页条数。

    返回:
        tuple[list[models.DspUpload], int]: (本页行实例列表, 全表总数)。

    异常:
        无业务异常。
    """
    total = db.execute(select(func.count()).select_from(models.DspUpload)).scalar() or 0
    rows = (
        db.execute(
            select(models.DspUpload)
            .order_by(models.DspUpload.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def list_rows(
    db, upload_id: int, *, page: int = 1, size: int = 100
) -> tuple[list[models.DspUploadRow], int]:
    """批次内事实行分页（按 id 升序），返回 (items, total)。

    参数:
        db: SQLAlchemy Session。
        upload_id: 批次主键（用于过滤事实行）。
        page: 页码（从 1 开始）。
        size: 每页条数。

    返回:
        tuple[list[models.DspUploadRow], int]: (本页事实行列表, 该批次内事实行总数)。

    异常:
        无业务异常。批次不存在时 `total == 0` 且 `items` 为空列表；调用方按需 404。
    """
    total = (
        db.execute(
            select(func.count())
            .select_from(models.DspUploadRow)
            .where(models.DspUploadRow.upload_id == upload_id)
        ).scalar()
        or 0
    )
    rows = (
        db.execute(
            select(models.DspUploadRow)
            .where(models.DspUploadRow.upload_id == upload_id)
            .order_by(models.DspUploadRow.id.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def delete_upload(db, upload_id: int) -> bool:
    """删除批次；ORM cascade + DB FK `ON DELETE CASCADE` 双轨保证事实行同步清空。

    参数:
        db: SQLAlchemy Session。
        upload_id: 批次主键。

    返回:
        bool: True 表示实际删除成功；False 表示批次不存在。

    异常:
        无业务异常。
    """
    upload = db.get(models.DspUpload, upload_id)
    if upload is None:
        return False
    db.delete(upload)
    db.commit()
    return True
