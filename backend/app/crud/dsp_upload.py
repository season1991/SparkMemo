"""DSP 上传 CRUD 操作（v0.5）。"""
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
    """按 (vendor, item, sub_item, version_date) 查询批次；存在返回行，不存在返回 None。"""
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
    """创建批次元数据行；唯一约束冲突时抛 IntegrityError。"""
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
    """批量插入事实行；用 session.add_all 让 SQLAlchemy 生成单条 multi-row INSERT。

    fact_rows 每项为字段名 -> 值的 dict；与 DspUploadRow 列名对应。
    """
    if not fact_rows:
        return
    db.add_all([models.DspUploadRow(upload_id=upload_id, **fr) for fr in fact_rows])
    db.commit()


def get_upload(db, upload_id: int) -> Optional[models.DspUpload]:
    """按主键查批次；不存在返回 None。"""
    return db.get(models.DspUpload, upload_id)


def list_uploads(db, *, page: int = 1, size: int = 20) -> tuple[list[models.DspUpload], int]:
    """批次列表（按 id 倒序），返回 (items, total)。"""
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
    """批次内事实行分页（按 id 升序），返回 (items, total)。"""
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
    """删除批次；外键 ON DELETE CASCADE 自动清空事实行。返回是否实际删除。"""
    upload = db.get(models.DspUpload, upload_id)
    if upload is None:
        return False
    db.delete(upload)
    db.commit()
    return True