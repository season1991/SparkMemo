# /api/tasks 路由
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from app import crud, models
from app.deps import get_db
from app.schemas import TaskListResponse
from app.services.scheduler import get_today


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _validate_create_payload(data: dict) -> tuple[dict, Optional[str]]:
    """校验任务创建请求体，返回 (cleaned_data, error_key)。"""
    company_id = data.get("company_id")
    project_id = data.get("project_id")
    due_at = data.get("due_at")

    if company_id is None:
        return {}, "company_id_missing"
    if project_id is None:
        return {}, "project_id_missing"
    if not due_at:
        return {}, "due_at_missing"
    return {
        "title": data.get("title"),
        "description": data.get("description"),
        "task_type_id": data.get("task_type_id"),
        "company_id": company_id,
        "project_id": project_id,
        "due_at": due_at,
        "remind_start_at": data.get("remind_start_at"),
    }, None


def _validate_update_payload(data: dict) -> tuple[dict, Optional[str]]:
    """校验任务更新请求体，返回 (cleaned_data, error_key)。"""
    due_at = data.get("due_at")
    remind_start_at = data.get("remind_start_at")
    if not due_at or not remind_start_at:
        return {}, "due_at_or_remind_start_missing"
    return {
        "title": data.get("title"),
        "description": data.get("description"),
        "task_type_id": data.get("task_type_id"),
        "company_id": data.get("company_id"),
        "project_id": data.get("project_id"),
        "due_at": due_at,
        "remind_start_at": remind_start_at,
    }, None


@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: Optional[str] = Query(None),
    company_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    task_type_id: Optional[int] = Query(None),
    due_from: Optional[str] = Query(None),
    due_to: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    remind_today: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """获取任务列表，支持多条件过滤和 remind_today 实时筛选。"""
    today_value = get_today() if remind_today else None
    try:
        items, total = crud.task.list_tasks(
            db,
            status_filter=status,
            company_id=company_id,
            project_id=project_id,
            task_type_id=task_type_id,
            due_from=due_from,
            due_to=due_to,
            keyword=keyword,
            remind_today=remind_today,
            today=today_value,
            page=page,
            size=size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "items": [crud.task.build_task_read(item) for item in items],
        "total": total,
    }


@router.post("", status_code=201)
def create_task(payload: dict, db=Depends(get_db)):
    """创建任务，含必填校验、日期校验和外键校验。"""
    cleaned, err = _validate_create_payload(payload)
    if err == "company_id_missing":
        raise HTTPException(status_code=400, detail="company_id is required")
    if err == "project_id_missing":
        raise HTTPException(status_code=400, detail="project_id is required")
    if err == "due_at_missing":
        raise HTTPException(status_code=400, detail="due_at is required")

    if db.get(models.Company, cleaned["company_id"]) is None:
        raise HTTPException(status_code=422, detail="company_id does not exist")
    if db.get(models.Project, cleaned["project_id"]) is None:
        raise HTTPException(status_code=422, detail="project_id does not exist")
    if cleaned["task_type_id"] is not None:
        if db.get(models.TaskType, cleaned["task_type_id"]) is None:
            raise HTTPException(status_code=422, detail="task_type_id does not exist")

    try:
        task = crud.task.create_task(db, **cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="task creation failed")
    return crud.task.build_task_read(task)


@router.get("/{task_id}")
def get_task(task_id: int, db=Depends(get_db)):
    """获取任务详情，含实时计算的提醒计划。"""
    task = crud.task.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return crud.task.build_task_read(task)


@router.put("/{task_id}")
def update_task(task_id: int, payload: dict, db=Depends(get_db)):
    """更新任务全部字段，保持 status 和 completed_at 不被隐式修改。"""
    cleaned, err = _validate_update_payload(payload)
    if err == "due_at_or_remind_start_missing":
        raise HTTPException(status_code=400, detail="due_at and remind_start_at are required")

    existing = crud.task.get_task(db, task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="task not found")

    if db.get(models.Company, cleaned["company_id"]) is None:
        raise HTTPException(status_code=422, detail="company_id does not exist")
    if db.get(models.Project, cleaned["project_id"]) is None:
        raise HTTPException(status_code=422, detail="project_id does not exist")
    if cleaned["task_type_id"] is not None:
        if db.get(models.TaskType, cleaned["task_type_id"]) is None:
            raise HTTPException(status_code=422, detail="task_type_id does not exist")

    try:
        task = crud.task.update_task(db, task_id, **cleaned)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="task update failed")
    return crud.task.build_task_read(task)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db=Depends(get_db)):
    """删除任务。"""
    if not crud.task.delete_task(db, task_id):
        raise HTTPException(status_code=404, detail="task not found")
    return None


@router.post("/{task_id}/complete")
def complete_task(task_id: int, db=Depends(get_db)):
    """标记任务为 completed，仅允许 pending → completed 跃迁。"""
    task, error = crud.task.complete_task(db, task_id, get_today())
    if error == "not_found":
        raise HTTPException(status_code=404, detail="task not found")
    if error == "not_pending":
        raise HTTPException(status_code=409, detail="task is not pending")
    return crud.task.build_task_read(task)