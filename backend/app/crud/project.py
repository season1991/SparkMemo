# 项目 CRUD 操作
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import models


def list_projects(
    db,
    company_id: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    size: int = 20,
):
    """查询项目列表，支持按公司和名称模糊搜索，返回 (items, total)。"""
    query = select(models.Project)
    count_query = select(func.count()).select_from(models.Project)

    if company_id is not None:
        query = query.where(models.Project.company_id == company_id)
        count_query = count_query.where(models.Project.company_id == company_id)
    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.where(models.Project.name.like(like_pattern))
        count_query = count_query.where(models.Project.name.like(like_pattern))

    total = db.execute(count_query).scalar() or 0
    query = query.order_by(models.Project.id).offset((page - 1) * size).limit(size)
    items = db.execute(query).scalars().all()
    return list(items), total


def get_project(db, project_id: int) -> Optional[models.Project]:
    """根据 id 查询项目，返回 None 表示不存在。"""
    return db.get(models.Project, project_id)


def create_project(
    db, company_id: int, name: str, notes: Optional[str] = None
) -> models.Project:
    """创建项目，唯一约束冲突时抛出 IntegrityError。"""
    project = models.Project(company_id=company_id, name=name, notes=notes)
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(project)
    return project


def update_project(
    db,
    project_id: int,
    company_id: int,
    name: str,
    notes: Optional[str] = None,
) -> Optional[models.Project]:
    """更新项目全部字段，返回更新后的对象或 None。"""
    project = db.get(models.Project, project_id)
    if project is None:
        return None
    project.company_id = company_id
    project.name = name
    project.notes = notes
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(project)
    return project


def delete_project(db, project_id: int) -> bool:
    """删除项目，返回 True 表示删除成功，False 表示不存在。"""
    project = db.get(models.Project, project_id)
    if project is None:
        return False
    db.delete(project)
    db.commit()
    return True