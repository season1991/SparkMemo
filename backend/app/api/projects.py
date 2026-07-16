# /api/projects 路由
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from app import crud, models
from app.deps import get_db
from app.schemas import ProjectListResponse, ProjectRead


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
def list_projects(
    company_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """获取项目列表，支持按公司筛选和名称模糊搜索。"""
    items, total = crud.project.list_projects(
        db, company_id=company_id, keyword=keyword, page=page, size=size
    )
    return {"items": [ProjectRead.model_validate(item) for item in items], "total": total}


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: dict, db=Depends(get_db)):
    """创建项目，company_id 缺失返回 400，无效返回 422，重名返回 409。"""
    company_id = payload.get("company_id")
    name = payload.get("name")
    notes = payload.get("notes")

    if company_id is None:
        raise HTTPException(status_code=400, detail="company_id is required")
    if db.get(models.Company, company_id) is None:
        raise HTTPException(status_code=422, detail="company_id does not exist")

    try:
        project = crud.project.create_project(db, company_id=company_id, name=name, notes=notes)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="project name already exists in this company")
    return ProjectRead.model_validate(project)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db=Depends(get_db)):
    """获取项目详情，不存在返回 404。"""
    project = crud.project.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectRead.model_validate(project)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: dict, db=Depends(get_db)):
    """更新项目全部字段。"""
    company_id = payload.get("company_id")
    name = payload.get("name")
    notes = payload.get("notes")

    try:
        project = crud.project.update_project(
            db, project_id, company_id=company_id, name=name, notes=notes
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="project name already exists in this company")
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db=Depends(get_db)):
    """删除项目。"""
    project = crud.project.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    crud.project.delete_project(db, project_id)
    return None