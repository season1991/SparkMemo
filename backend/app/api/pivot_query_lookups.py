"""/api/pivot-query/lookups 路由（v0.5.6 — 透视查询辅助 lookup）。

错误约定：
- 400：参数非法（如 month 不在 1-12）
- 500：SQLAlchemy 异常（如 week_dt 表不存在 / DB 不可达）

仅 GET；纯只读，不修改任何数据。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app import crud
from app.deps import get_db
from app.schemas import WeekInfo


router = APIRouter(
    prefix="/api/pivot-query/lookups",
    tags=["pivot-query-lookups"],
)


@router.get("/countries", response_model=list[str])
def get_business_countries(
    vendor: str = Query(..., min_length=1, max_length=64),
    item: str = Query(..., min_length=1, max_length=128),
    sub_item: str = Query(..., min_length=1, max_length=128),
    version_dates: str | None = Query(None, description="逗号分隔 YYYY-MM-DD；空=不限"),
    db=Depends(get_db),
):
    """返回指定 (vendor+item+sub_item+version_dates) 下所有去重 country。

    注：仅 Demand 行纳入（与透视查询主路径对齐）。
    """
    return crud.pivot_query_lookups.distinct_countries(
        db,
        vendor=vendor,
        item=item,
        sub_item=sub_item,
        version_dates_csv=version_dates,
    )


@router.get("/categories", response_model=list[str])
def get_business_categories(
    vendor: str = Query(..., min_length=1, max_length=64),
    item: str = Query(..., min_length=1, max_length=128),
    sub_item: str = Query(..., min_length=1, max_length=128),
    version_dates: str | None = Query(None, description="逗号分隔 YYYY-MM-DD；空=不限"),
    countries: str | None = Query(None, description="逗号分隔 country；空=不限"),
    db=Depends(get_db),
):
    """返回指定条件下（已选 countries 时再过滤）去重 category。"""
    return crud.pivot_query_lookups.distinct_categories(
        db,
        vendor=vendor,
        item=item,
        sub_item=sub_item,
        version_dates_csv=version_dates,
        countries_csv=countries,
    )


@router.get("/config-names", response_model=list[str])
def get_business_config_names(
    vendor: str = Query(..., min_length=1, max_length=64),
    item: str = Query(..., min_length=1, max_length=128),
    sub_item: str = Query(..., min_length=1, max_length=128),
    version_dates: str | None = Query(None, description="逗号分隔 YYYY-MM-DD；空=不限"),
    countries: str | None = Query(None, description="逗号分隔 country；空=不限"),
    categories: str | None = Query(None, description="逗号分隔 category；空=不限"),
    db=Depends(get_db),
):
    """返回指定条件下（已选 countries + categories 时再过滤）去重 config_name。"""
    return crud.pivot_query_lookups.distinct_config_names(
        db,
        vendor=vendor,
        item=item,
        sub_item=sub_item,
        version_dates_csv=version_dates,
        countries_csv=countries,
        categories_csv=categories,
    )


@router.get("/weeks-of-month", response_model=list[WeekInfo])
def get_weeks_of_month(
    year: int = Query(..., ge=1970, le=2100, description="ISO 年（week_id 所属年份）"),
    month: int = Query(..., ge=1, le=12, description="自然月 1-12"),
    db=Depends(get_db),
):
    """返回指定 ISO 年 + 自然月的所有 (week_id, week_start_date)。

    - week_id：ISO 周编号 1-53
    - week_start_date：该周周一的日期（YYYY-MM-DD）
    - 按 dt 升序
    """
    try:
        return crud.pivot_query_lookups.weeks_of_month(db, year=year, month=month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc