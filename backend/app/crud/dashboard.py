"""今日概述聚合查询 - 单次 SQL 完成 LEFT JOIN 全公司 + 严格基线下的三档分桶。

遵循 spec/dashboard.md：
  - 严格基线：status='pending' AND remind_start_at<=today AND due_at>=today
  - 三档：CASE WHEN 互斥且穷尽；total 单独 SUM（防止 COUNT/SUM 失误）
  - SQL 文本不含 CURDATE() / NOW() / CURRENT_DATE / GETDATE()；
    today 与 soon_cutoff 都由 Python 层 date.today() 计算后作为命名参数传入。
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text


def count_tasks_by_company_for_today(db, today: str) -> list[dict]:
    """聚合每家公司在严格基线下的三档分桶计数。

    Args:
        db: SQLAlchemy Session（无外键依赖，纯聚合查询）。
        today: YYYY-MM-DD；由调用方（路由层通过 services.scheduler.get_today）传入。

    Returns:
        list[dict]: 每个元素包含 company_id / company_name / urgent / due_soon / early / total；
        LEFT JOIN 后即使 0 任务公司也会有一行；companies 表为空时返回 []。
        排序固定为 `total DESC, urgent DESC, company_name ASC`（由 SQL 完成）。
    """
    # 截止边界：today + 3 天；Python 层计算后作为命名参数传入，避免依赖 DB 内置日期函数。
    soon_cutoff = (date.fromisoformat(today) + timedelta(days=3)).isoformat()

    sql = text("""
        SELECT
          c.id   AS company_id,
          c.name AS company_name,
          SUM(CASE
                WHEN t.status = 'pending'
                 AND t.remind_start_at <= :today
                 AND t.due_at >= :today
                 AND t.due_at <= :today
                THEN 1 ELSE 0 END) AS urgent,
          SUM(CASE
                WHEN t.status = 'pending'
                 AND t.remind_start_at <= :today
                 AND t.due_at >= :today
                 AND t.due_at >  :today
                 AND t.due_at <= :soon_cutoff
                THEN 1 ELSE 0 END) AS due_soon,
          SUM(CASE
                WHEN t.status = 'pending'
                 AND t.remind_start_at <= :today
                 AND t.due_at >= :today
                 AND t.due_at >  :soon_cutoff
                THEN 1 ELSE 0 END) AS early,
          SUM(CASE
                WHEN t.status = 'pending'
                 AND t.remind_start_at <= :today
                 AND t.due_at >= :today
                THEN 1 ELSE 0 END) AS total
        FROM companies c
        LEFT JOIN tasks t ON t.company_id = c.id
        GROUP BY c.id, c.name
        ORDER BY total DESC, urgent DESC, c.name ASC
    """)

    rows = db.execute(sql, {"today": today, "soon_cutoff": soon_cutoff}).fetchall()

    return [
        {
            "company_id": r.company_id,
            "company_name": r.company_name,
            "urgent": int(r.urgent or 0),
            "due_soon": int(r.due_soon or 0),
            "early": int(r.early or 0),
            "total": int(r.total or 0),
        }
        for r in rows
    ]
