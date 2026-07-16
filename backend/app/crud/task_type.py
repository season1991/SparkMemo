# 任务类型 CRUD 操作
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import models


def list_task_types(db) -> list[models.TaskType]:
    """查询全量任务类型列表，不分页。"""
    query = select(models.TaskType).order_by(models.TaskType.id)
    return list(db.execute(query).scalars().all())


def get_task_type(db, task_type_id: int) -> Optional[models.TaskType]:
    """根据 id 查询任务类型，返回 None 表示不存在。"""
    return db.get(models.TaskType, task_type_id)


def create_task_type(db, name: str) -> models.TaskType:
    """创建任务类型，唯一约束冲突时抛出 IntegrityError。"""
    task_type = models.TaskType(name=name)
    db.add(task_type)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(task_type)
    return task_type


def update_task_type(db, task_type_id: int, name: str) -> Optional[models.TaskType]:
    """更新任务类型名称，返回更新后的对象或 None。"""
    task_type = db.get(models.TaskType, task_type_id)
    if task_type is None:
        return None
    task_type.name = name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(task_type)
    return task_type


def delete_task_type(db, task_type_id: int) -> bool:
    """删除任务类型，返回 True 表示删除成功，False 表示不存在。"""
    task_type = db.get(models.TaskType, task_type_id)
    if task_type is None:
        return False
    db.delete(task_type)
    db.commit()
    return True


def has_references(db, task_type_id: int) -> bool:
    """检查任务类型是否被任务引用。"""
    task_count = db.execute(
        select(func.count())
        .select_from(models.Task)
        .where(models.Task.task_type_id == task_type_id)
    ).scalar() or 0
    return task_count > 0