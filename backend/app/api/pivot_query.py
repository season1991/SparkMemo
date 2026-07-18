"""/api/pivot-query 路由（v0.5.6 — 透视查询）。

错误约定：
- 422：Pydantic 级联校验失败（业务行/时间维度）/ 笛卡尔积预检超出 MAX_CARTESIAN
- 500：SQLAlchemy 异常（如 week_dt 表不存在）

业务范围（v0.5.6）：
- 仅支持 `pivot_type='demand'`（固定注入 `data_type='Demand'`）
- `pivot_type='demand_plus_supply'` 占位（Schema 接受但行为等同 'demand'，留给后续实现）
- 不涉及 dsp_uploads 的上传/查询/删除子功能；纯只读
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import crud
from app.deps import get_db
from app.schemas import PivotQueryRequest, PivotQueryResponse


router = APIRouter(prefix="/api/pivot-query", tags=["pivot-query"])


@router.post("", response_model=PivotQueryResponse)
def pivot_query_endpoint(
    req: PivotQueryRequest,
    db=Depends(get_db),
):
    """透视查询：横向业务行 × 纵向日期 × 交叉点 quantity。

    流程：
    1. Pydantic 自动校验 `pivot_type` / `vendor` / `item` / `sub_item` / `version_dates` 与
       业务行级联 / 时间维度级联 / 至少一个时间维度 → 失败时 FastAPI 自动 422
    2. CRUD 层 `estimate_size()` 估算笛卡尔积 → 超出 `MAX_CARTESIAN` 时返回 422
    3. CRUD 层 `query_pivot()` 执行 CTE 共享查询，返回长格式响应

    参数:
        req: 透视查询请求体（Body）。
        db: FastAPI 注入的数据库 Session。

    返回:
        PivotQueryResponse: 含 `period_columns` / `row_groups` / `total_rows` /
        `version_dates` / `date_granularity` 的响应。

    异常:
        HTTPException 422: 笛卡尔积预检超出 MAX_CARTESIAN（50000）。
        HTTPException 500: SQLAlchemy 异常（如 week_dt 表不存在）。
    """
    estimated = crud.pivot_query.estimate_size(db, req)
    if estimated > crud.pivot_query.MAX_CARTESIAN:
        raise HTTPException(
            status_code=422,
            detail=(
                f"cartesian product estimated {estimated} rows exceeds limit "
                f"{crud.pivot_query.MAX_CARTESIAN}; please narrow business row "
                f"filters or date range"
            ),
        )

    return crud.pivot_query.query_pivot(db, req)