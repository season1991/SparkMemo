"""/api/pivot-query 路由（v0.5.7 — 透视查询）。

v0.5.7 业务范围：
- 支持 `pivot_type='demand'`：固定注入 `data_type='Demand'`
- 支持 `pivot_type='demand_plus_supply'`：SQL `base_rows` CTE 改为 `IN ('Demand', 'Supply')`，
  b 子查询 GROUP BY 去掉 `data_type`，Python 层派生 `TTL_GAP` / `Rolling_TTLGAP` 两行
  （详见 spec §11 / crud/pivot_query.py）
- 不涉及 dsp_uploads 的上传/查询/删除子功能；纯只读

错误约定：
- 422：Pydantic 级联校验失败（业务行 / 时间维度 / `demand_plus_supply` 时 version_dates ≠ 1）
  / 笛卡尔积预检超出 MAX_CARTESIAN
- 500：SQLAlchemy 异常（如 week_dt 表不存在）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app import crud
from app.deps import get_db
from app.schemas import PivotQueryRequest, PivotQueryResponse
from app.services.excel_export import _export_timestamp, build_pivot_xlsx


router = APIRouter(prefix="/api/pivot-query", tags=["pivot-query"])

XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


# ==================== v0.5.8 Excel 导出 ====================


@router.post("/export")
def pivot_export_endpoint(
    req: PivotQueryRequest,
    db=Depends(get_db),
):
    """把透视查询结果导出为 .xlsx（sheet 1「透视结果」+ sheet 2「查询参数快照」）。

    Body 与 `POST /api/pivot-query` 完全一致；Pydantic 校验复用同一 schema。

    文件名：`pivot_{pivot_type}_{YYYYMMDD_HHMMSS}.xlsx`，纯 ASCII。

    参数:
        req: 透视查询请求体（Body）。
        db: FastAPI 注入的数据库 Session。

    返回:
        StreamingResponse: xlsx 二进制流 + `Content-Disposition: attachment; filename="..."`。

    异常:
        HTTPException 422: Pydantic 级联校验失败 / 笛卡尔积超限 /
            `demand_plus_supply` 多 version_date。
        HTTPException 500: SQLAlchemy / pandas / openpyxl 异常。
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

    resp = crud.pivot_query.query_pivot(db, req)
    content = build_pivot_xlsx(req, resp)
    filename = f"pivot_{req.pivot_type}_{_export_timestamp()}.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type=XLSX_CT,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )