# /api/companies 路由
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from app import crud
from app.deps import get_db
from app.schemas import CompanyCreate, CompanyListResponse, CompanyRead, CompanyUpdate


router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=CompanyListResponse)
def list_companies(
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """获取公司列表，支持名称模糊搜索和分页。"""
    items, total = crud.company.list_companies(db, keyword=keyword, page=page, size=size)
    return {"items": [CompanyRead.model_validate(item) for item in items], "total": total}


@router.post("", response_model=CompanyRead, status_code=201)
def create_company(payload: CompanyCreate, db=Depends(get_db)):
    """创建公司，name 必填且全表唯一。"""
    try:
        company = crud.company.create_company(db, name=payload.name, notes=payload.notes)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="company name already exists")
    return CompanyRead.model_validate(company)


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(company_id: int, db=Depends(get_db)):
    """获取公司详情，不存在返回 404。"""
    company = crud.company.get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return CompanyRead.model_validate(company)


@router.put("/{company_id}", response_model=CompanyRead)
def update_company(company_id: int, payload: CompanyUpdate, db=Depends(get_db)):
    """更新公司名称和备注。"""
    try:
        company = crud.company.update_company(
            db, company_id, name=payload.name, notes=payload.notes
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="company name already exists")
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    return CompanyRead.model_validate(company)


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: int, db=Depends(get_db)):
    """删除公司，被项目或任务引用时返回 409。"""
    company = crud.company.get_company(db, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="company not found")
    if crud.company.has_references(db, company_id):
        raise HTTPException(status_code=409, detail="company is referenced by projects or tasks")
    crud.company.delete_company(db, company_id)
    return None