"""今日概述接口 - GET /api/dashboard/today。

只读聚合接口；无路径参数 / 无 query 参数。
"""
from fastapi import APIRouter, Depends

from app import crud, schemas
from app.deps import get_db
from app.services.scheduler import get_today


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/today", response_model=schemas.DashboardTodayResponse)
def get_dashboard_today(db=Depends(get_db)) -> dict:
    """今日概述：返回 today + summary + companies[]。

    - today: 服务端通过 scheduler.get_today() 取当前日期（与 check_overdue_tasks 同源）。
    - summary: 由 companies[] 在 Python 层求和得到，保持唯一真理源，避免 SQL 与 Python 双源。
    - companies: 由 crud.dashboard 单次聚合 SQL 返回，包含所有公司（0 任务也列出）。
    """
    today = get_today()
    rows = crud.dashboard.count_tasks_by_company_for_today(db, today)

    summary = {
        "urgent": sum(r["urgent"] for r in rows),
        "due_soon": sum(r["due_soon"] for r in rows),
        "early": sum(r["early"] for r in rows),
        "total": sum(r["total"] for r in rows),
    }

    return {
        "today": today,
        "summary": summary,
        "companies": rows,
    }
