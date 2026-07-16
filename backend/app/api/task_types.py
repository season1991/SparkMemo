# /api/task-types 路由
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from app import crud
from app.deps import get_db
from app.schemas import TaskTypeRead


router = APIRouter(prefix="/api/task-types", tags=["task-types"])


@router.get("", response_model=list[TaskTypeRead])
def list_task_types(db=Depends(get_db)):
    """获取全量任务类型列表，不分页。"""
    items = crud.task_type.list_task_types(db)
    return [TaskTypeRead.model_validate(item) for item in items]


@router.post("", response_model=TaskTypeRead, status_code=201)
def create_task_type(payload: dict, db=Depends(get_db)):
    """创建任务类型，name 全表唯一。"""
    name = payload.get("name")
    try:
        task_type = crud.task_type.create_task_type(db, name=name)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="task type name already exists")
    return TaskTypeRead.model_validate(task_type)


@router.get("/{task_type_id}", response_model=TaskTypeRead)
def get_task_type(task_type_id: int, db=Depends(get_db)):
    """获取任务类型详情，不存在返回 404。"""
    task_type = crud.task_type.get_task_type(db, task_type_id)
    if task_type is None:
        raise HTTPException(status_code=404, detail="task type not found")
    return TaskTypeRead.model_validate(task_type)


@router.put("/{task_type_id}", response_model=TaskTypeRead)
def update_task_type(task_type_id: int, payload: dict, db=Depends(get_db)):
    """更新任务类型名称。"""
    name = payload.get("name")
    try:
        task_type = crud.task_type.update_task_type(db, task_type_id, name=name)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="task type name already exists")
    if task_type is None:
        raise HTTPException(status_code=404, detail="task type not found")
    return TaskTypeRead.model_validate(task_type)


@router.delete("/{task_type_id}", status_code=204)
def delete_task_type(task_type_id: int, db=Depends(get_db)):
    """删除任务类型，被任务引用时返回 409。"""
    task_type = crud.task_type.get_task_type(db, task_type_id)
    if task_type is None:
        raise HTTPException(status_code=404, detail="task type not found")
    if crud.task_type.has_references(db, task_type_id):
        raise HTTPException(status_code=409, detail="task type is referenced by tasks")
    crud.task_type.delete_task_type(db, task_type_id)
    return None