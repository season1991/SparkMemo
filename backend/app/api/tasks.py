# /api/tasks 路由
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from app import crud, models, schemas
from app.deps import get_db
from app.services.reminders import resolve_remind_start_at
from app.services.scheduler import get_today


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _translate_or_400(payload: schemas.TaskCreate | schemas.TaskUpdate) -> str:
    """调用 resolve_remind_start_at 翻译 remind_rule；捕获 ValueError 转 400。"""
    try:
        return resolve_remind_start_at(
            due_at=payload.due_at,
            remind_rule=payload.remind_rule,
            custom_remind_start_at=payload.custom_remind_start_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=schemas.TaskListResponse)
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
def create_task(payload: schemas.TaskCreate, db=Depends(get_db)):
    """创建任务：校验必填 + 翻译 remind_rule -> remind_start_at + 外键存在性。"""
    # remind_rule 字段已由 Pydantic Literal 校验；这里再翻译
    resolved_start_at = _translate_or_400(payload)

    if db.get(models.Company, payload.company_id) is None:
        raise HTTPException(status_code=422, detail="company_id does not exist")
    if db.get(models.Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail="project_id does not exist")
    if payload.task_type_id is not None:
        if db.get(models.TaskType, payload.task_type_id) is None:
            raise HTTPException(status_code=422, detail="task_type_id does not exist")

    try:
        task = crud.task.create_task(
            db,
            title=payload.title,
            description=payload.description,
            task_type_id=payload.task_type_id,
            company_id=payload.company_id,
            project_id=payload.project_id,
            due_at=payload.due_at,
            remind_start_at=resolved_start_at,
        )
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
def update_task(task_id: int, payload: schemas.TaskUpdate, db=Depends(get_db)):
    """更新任务全部字段；remind_rule + due_at 一并提交后由后端翻译回 remind_start_at。"""
    resolved_start_at = _translate_or_400(payload)

    existing = crud.task.get_task(db, task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="task not found")

    if db.get(models.Company, payload.company_id) is None:
        raise HTTPException(status_code=422, detail="company_id does not exist")
    if db.get(models.Project, payload.project_id) is None:
        raise HTTPException(status_code=422, detail="project_id does not exist")
    if payload.task_type_id is not None:
        if db.get(models.TaskType, payload.task_type_id) is None:
            raise HTTPException(status_code=422, detail="task_type_id does not exist")

    try:
        task = crud.task.update_task(
            db,
            task_id,
            title=payload.title,
            description=payload.description,
            task_type_id=payload.task_type_id,
            company_id=payload.company_id,
            project_id=payload.project_id,
            due_at=payload.due_at,
            remind_start_at=resolved_start_at,
        )
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
