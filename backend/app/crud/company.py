# 公司 CRUD 操作
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import models


def list_companies(db, keyword: Optional[str] = None, page: int = 1, size: int = 20):
    """查询公司列表，支持按名称模糊搜索，返回 (items, total)。"""
    query = select(models.Company)
    count_query = select(func.count()).select_from(models.Company)

    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.where(models.Company.name.like(like_pattern))
        count_query = count_query.where(models.Company.name.like(like_pattern))

    total = db.execute(count_query).scalar() or 0
    query = query.order_by(models.Company.id).offset((page - 1) * size).limit(size)
    items = db.execute(query).scalars().all()
    return list(items), total


def get_company(db, company_id: int) -> Optional[models.Company]:
    """根据 id 查询公司，返回 None 表示不存在。"""
    return db.get(models.Company, company_id)


def create_company(db, name: str, notes: Optional[str] = None) -> models.Company:
    """创建公司，唯一约束冲突时抛出 IntegrityError。"""
    company = models.Company(name=name, notes=notes)
    db.add(company)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(company)
    return company


def update_company(db, company_id: int, name: str, notes: Optional[str] = None) -> Optional[models.Company]:
    """更新公司全部字段，返回更新后的对象或 None。"""
    company = db.get(models.Company, company_id)
    if company is None:
        return None
    company.name = name
    company.notes = notes
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(company)
    return company


def delete_company(db, company_id: int) -> bool:
    """删除公司，返回 True 表示删除成功，False 表示不存在。"""
    company = db.get(models.Company, company_id)
    if company is None:
        return False
    db.delete(company)
    db.commit()
    return True


def has_references(db, company_id: int) -> bool:
    """检查公司是否被项目或任务引用。"""
    project_count = db.execute(
        select(func.count()).select_from(models.Project).where(models.Project.company_id == company_id)
    ).scalar() or 0
    if project_count > 0:
        return True
    task_count = db.execute(
        select(func.count()).select_from(models.Task).where(models.Task.company_id == company_id)
    ).scalar() or 0
    return task_count > 0