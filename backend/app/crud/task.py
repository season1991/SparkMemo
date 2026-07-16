# 任务 CRUD 操作
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import models
from app.services import reminders as reminder_service


def _validate_date(value: str, field: str) -> str:
    """校验 YYYY-MM-DD 格式并返回原值，无效抛出 ValueError。"""
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc
    return value


def _resolve_remind_start(due_at: str, remind_start_at: Optional[str]) -> str:
    """校验日期格式并解析 remind_start_at，缺省取 due_at - 1 天。"""
    due_value = _validate_date(due_at, "due_at")
    if remind_start_at is None:
        return (date.fromisoformat(due_value) - timedelta(days=1)).isoformat()
    start_value = _validate_date(remind_start_at, "remind_start_at")
    if start_value > due_value:
        raise ValueError("remind_start_at must be <= due_at")
    return start_value


def list_tasks(
    db,
    *,
    status_filter: Optional[str] = None,
    company_id: Optional[int] = None,
    project_id: Optional[int] = None,
    task_type_id: Optional[int] = None,
    due_from: Optional[str] = None,
    due_to: Optional[str] = None,
    keyword: Optional[str] = None,
    remind_today: bool = False,
    today: Optional[str] = None,
    page: int = 1,
    size: int = 20,
):
    """查询任务列表，支持多条件过滤和 remind_today 实时筛选，返回 (items, total)。"""
    query = select(models.Task).options(
        selectinload(models.Task.company),
        selectinload(models.Task.project),
        selectinload(models.Task.task_type),
    )
    count_query = select(func.count()).select_from(models.Task)

    filters = []
    if status_filter:
        filters.append(models.Task.status == status_filter)
    if company_id is not None:
        filters.append(models.Task.company_id == company_id)
    if project_id is not None:
        filters.append(models.Task.project_id == project_id)
    if task_type_id is not None:
        filters.append(models.Task.task_type_id == task_type_id)
    if due_from:
        _validate_date(due_from, "due_from")
        filters.append(models.Task.due_at >= due_from)
    if due_to:
        _validate_date(due_to, "due_to")
        filters.append(models.Task.due_at <= due_to)
    if keyword:
        like_pattern = f"%{keyword}%"
        filters.append(models.Task.title.like(like_pattern))
    if remind_today:
        if not today:
            raise ValueError("today is required when remind_today=True")
        filters.append(
            and_(
                models.Task.status == "pending",
                models.Task.remind_start_at <= today,
                models.Task.due_at >= today,
            )
        )

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = db.execute(count_query).scalar() or 0
    query = query.order_by(models.Task.id).offset((page - 1) * size).limit(size)
    items = db.execute(query).scalars().all()
    return list(items), total


def get_task(db, task_id: int) -> Optional[models.Task]:
    """根据 id 查询任务并预加载外键关联，返回 None 表示不存在。"""
    query = (
        select(models.Task)
        .options(
            selectinload(models.Task.company),
            selectinload(models.Task.project),
            selectinload(models.Task.task_type),
        )
        .where(models.Task.id == task_id)
    )
    return db.execute(query).scalar_one_or_none()


def create_task(
    db,
    *,
    title: str,
    description: Optional[str],
    task_type_id: Optional[int],
    company_id: int,
    project_id: int,
    due_at: str,
    remind_start_at: Optional[str],
) -> models.Task:
    """创建任务，自动处理 remind_start_at 缺省和日期校验。"""
    resolved_start = _resolve_remind_start(due_at, remind_start_at)
    task = models.Task(
        title=title,
        description=description,
        task_type_id=task_type_id,
        company_id=company_id,
        project_id=project_id,
        due_at=due_at,
        remind_start_at=resolved_start,
        status="pending",
    )
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(task)
    return task


def update_task(
    db,
    task_id: int,
    *,
    title: str,
    description: Optional[str],
    task_type_id: Optional[int],
    company_id: int,
    project_id: int,
    due_at: str,
    remind_start_at: str,
) -> Optional[models.Task]:
    """更新任务全部字段，保持 status 和 completed_at 不被隐式修改。"""
    task = db.get(models.Task, task_id)
    if task is None:
        return None
    resolved_start = _resolve_remind_start(due_at, remind_start_at)
    task.title = title
    task.description = description
    task.task_type_id = task_type_id
    task.company_id = company_id
    task.project_id = project_id
    task.due_at = due_at
    task.remind_start_at = resolved_start
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(task)
    return task


def delete_task(db, task_id: int) -> bool:
    """删除任务，返回 True 表示删除成功，False 表示不存在。"""
    task = db.get(models.Task, task_id)
    if task is None:
        return False
    db.delete(task)
    db.commit()
    return True


def complete_task(db, task_id: int, today: str) -> tuple[Optional[models.Task], Optional[str]]:
    """
    标记任务为 completed。

    返回 (task, error_key):
        task 不为 None 表示成功，error_key 为 "not_found" / "not_pending" 时表示失败原因。
    """
    task = db.get(models.Task, task_id)
    if task is None:
        return None, "not_found"
    if task.status != "pending":
        return None, "not_pending"
    task.status = "completed"
    task.completed_at = today
    db.commit()
    db.refresh(task)
    return task, None


def build_task_read(task: models.Task) -> dict:
    """将 ORM Task 对象序列化为详情响应 dict，包含实时计算的 reminders。"""
    reminder_list = reminder_service.compute_reminders(
        task.remind_start_at, task.due_at
    )
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "task_type": (
            {"id": task.task_type.id, "name": task.task_type.name}
            if task.task_type
            else None
        ),
        "company": {"id": task.company.id, "name": task.company.name},
        "project": {"id": task.project.id, "name": task.project.name},
        "due_at": task.due_at,
        "remind_start_at": task.remind_start_at,
        "status": task.status,
        "completed_at": task.completed_at,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "reminders": reminder_list,
    }