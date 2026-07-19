"""透视查询 CRUD（v0.5.7）。

设计要点（与 spec §透视查询 / §11 Demand+Supply 计算规则 对齐）：
1. 三子查询拼接：横向（dsp_uploads × dsp_upload_rows 业务行去重）× 纵向（week_dt）× 交叉点（dsp_upload_rows 明细 quantity）。
2. 共享 CTE：b 与 d 子查询都从同一个 `base_rows` CTE 中取，**只扫描一次 dsp_upload_rows**。
3. 笛卡尔积在数据库层通过 SQL JOIN 自然展开，无 GROUP BY 即可获得「每行 × 每日期 = 一条记录」。
4. 数据量保护：`estimate_size()` 在执行前估算 `|b| × |c|`，超出 `MAX_CARTESIAN` 由路由层返回 422。
5. 不依赖 DB 日期函数：所有日期范围在 Python 层构造后作为参数传入。
6. v0.5.7 新增 `pivot_type='demand_plus_supply'` 分支：
   - `base_rows` CTE 过滤改为 `data_type IN ('Demand', 'Supply')`
   - b 子查询 GROUP BY **去掉 data_type**，让 Demand / Supply 配对到同一业务组
   - d 子查询保留 data_type 字段，Python 层按 §11.3 七步计算 Demand / Supply / TTL_GAP / Rolling_TTLGAP 四行/组

不抛 4xx HTTPException；业务异常（如 week_dt 表不存在）由调用方按场景映射。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from app import models
from app.schemas import PivotQueryRequest, PivotQueryResponse, PivotRow


# 笛卡尔积硬上限：超出 → 422 拒绝执行
MAX_CARTESIAN = 50000


def _build_base_rows_filters(req: PivotQueryRequest) -> list:
    """构造 base_rows CTE 的筛选条件（b 与 d 共享）。

    v0.5.7 变更：
    - `pivot_type='demand'` 固定过滤 `data_type='Demand'`
    - `pivot_type='demand_plus_supply'` 改为 `data_type IN ('Demand', 'Supply')`
    """
    filters = [
        models.DspUploadRow.upload_id == models.DspUpload.id,
        models.DspUpload.vendor == req.vendor,
        models.DspUpload.item == req.item,
        models.DspUpload.sub_item == req.sub_item,
        models.DspUpload.version_date.in_(req.version_dates),
    ]
    if req.pivot_type == "demand_plus_supply":
        filters.append(
            models.DspUploadRow.data_type.in_(["Demand", "Supply"])
        )
    else:
        # 保持 v0.5.6 行为：固定 Demand
        filters.append(models.DspUploadRow.data_type == "Demand")
    if req.countries:
        filters.append(models.DspUploadRow.country.in_(req.countries))
    if req.categories:
        filters.append(models.DspUploadRow.category.in_(req.categories))
    if req.config_codes:
        filters.append(models.DspUploadRow.config_code.in_(req.config_codes))
    if req.config_names:
        filters.append(models.DspUploadRow.config_name.in_(req.config_names))
    return filters


def estimate_size(db: Session, req: PivotQueryRequest) -> int:
    """估算笛卡尔积规模 `|b| × |c|`，超限由路由层拒绝。

    - `|b|` = 命中行经 `country, category, config_code, config_name, data_type, ttl, upload_id` 去重后的业务行数
      - `pivot_type='demand_plus_supply'` 时按业务维度（不含 data_type）配对 Demand/Supply，所以 GROUP BY 字段
        同样要去掉 data_type
    - `|c|` = 命中的纵向日期数

    参数:
        db: SQLAlchemy Session
        req: 透视查询请求体（已通过 Pydantic 校验）

    返回:
        int: 笛卡尔积行数；`|b| == 0` 或 `|c| == 0` 时直接返回 0

    异常:
        无业务异常；SQLAlchemy 报错时由 FastAPI 映射为 500
    """
    b_filters = _build_base_rows_filters(req)

    # b 子查询字段集合
    if req.pivot_type == "demand_plus_supply":
        # 配对模式：去掉 data_type
        b_cols = [
            models.DspUploadRow.country,
            models.DspUploadRow.category,
            models.DspUploadRow.config_code,
            models.DspUploadRow.config_name,
            models.DspUploadRow.ttl,
            models.DspUploadRow.upload_id,
        ]
    else:
        b_cols = [
            models.DspUploadRow.country,
            models.DspUploadRow.category,
            models.DspUploadRow.config_code,
            models.DspUploadRow.config_name,
            models.DspUploadRow.data_type,
            models.DspUploadRow.ttl,
            models.DspUploadRow.upload_id,
        ]

    b_sub = (
        select(*b_cols)
        .select_from(models.DspUploadRow)
        .join(models.DspUpload, models.DspUploadRow.upload_id == models.DspUpload.id)
        .where(*b_filters)
        .distinct()
        .subquery()
    )
    b_count = (
        db.execute(select(func.count()).select_from(b_sub)).scalar() or 0
    )

    if b_count == 0:
        return 0

    c_filters = []
    if req.years:
        c_filters.append(models.WeekDt.year_id.in_(req.years))
    if req.months:
        c_filters.append(models.WeekDt.month_id.in_(req.months))
    if req.weeks:
        c_filters.append(models.WeekDt.week_id.in_(req.weeks))
    if not req.expand_to_daily:
        c_filters.append(models.WeekDt.is_week_start == True)  # noqa: E712

    c_count = (
        db.execute(
            select(func.count())
            .select_from(models.WeekDt)
            .where(*c_filters)
        ).scalar()
        or 0
    )

    return b_count * c_count


def _build_a_subquery(req: PivotQueryRequest):
    """构造 a 子查询（dsp_uploads 维度）。"""
    return (
        select(
            models.DspUpload.id.label("upload_id"),
            models.DspUpload.version_date.label("version_date"),
        )
        .where(models.DspUpload.vendor == req.vendor)
        .where(models.DspUpload.item == req.item)
        .where(models.DspUpload.sub_item == req.sub_item)
        .where(models.DspUpload.version_date.in_(req.version_dates))
        .subquery("a")
    )


def _build_c_subquery(req: PivotQueryRequest):
    """构造 c 子查询（week_dt 维度，按 expand_to_daily 决定过滤 is_week_start）。"""
    c_filters = []
    if req.years:
        c_filters.append(models.WeekDt.year_id.in_(req.years))
    if req.months:
        c_filters.append(models.WeekDt.month_id.in_(req.months))
    if req.weeks:
        c_filters.append(models.WeekDt.week_id.in_(req.weeks))
    if not req.expand_to_daily:
        c_filters.append(models.WeekDt.is_week_start == True)  # noqa: E712
    return (
        select(models.WeekDt.dt.label("period_date"))
        .where(*c_filters)
        .subquery("c")
    )


def _query_demand(db: Session, req: PivotQueryRequest) -> PivotQueryResponse:
    """v0.5.6 原 demand 模式：b 子查询 GROUP BY 含 data_type，输出每业务维度一行。"""
    filters = _build_base_rows_filters(req)

    # base_rows CTE
    base_rows = (
        select(
            models.DspUploadRow.id.label("row_id"),
            models.DspUploadRow.upload_id.label("upload_id"),
            models.DspUploadRow.country.label("country"),
            models.DspUploadRow.category.label("category"),
            models.DspUploadRow.config_code.label("config_code"),
            models.DspUploadRow.config_name.label("config_name"),
            models.DspUploadRow.data_type.label("data_type"),
            models.DspUploadRow.ttl.label("ttl"),
            models.DspUploadRow.date.label("row_date"),
            models.DspUploadRow.quantity.label("quantity"),
        )
        .join(models.DspUpload, models.DspUploadRow.upload_id == models.DspUpload.id)
        .where(*filters)
        .cte("base_rows")
    )

    sub_a = _build_a_subquery(req)
    sub_c = _build_c_subquery(req)

    # b 子查询：含 data_type（demand 模式按 (..., data_type, ttl) 去重）
    sub_b = (
        select(
            base_rows.c.upload_id.label("upload_id"),
            base_rows.c.country.label("country"),
            base_rows.c.category.label("category"),
            base_rows.c.config_code.label("config_code"),
            base_rows.c.config_name.label("config_name"),
            base_rows.c.data_type.label("data_type"),
            base_rows.c.ttl.label("ttl"),
        )
        .select_from(base_rows)
        .group_by(
            base_rows.c.upload_id,
            base_rows.c.country,
            base_rows.c.category,
            base_rows.c.config_code,
            base_rows.c.config_name,
            base_rows.c.data_type,
            base_rows.c.ttl,
        )
        .subquery("b")
    )

    # d 子查询：明细 (country, category, code, name, data_type, ttl, row_date, quantity)
    sub_d = (
        select(
            base_rows.c.upload_id.label("upload_id"),
            base_rows.c.country.label("country"),
            base_rows.c.category.label("category"),
            base_rows.c.config_code.label("config_code"),
            base_rows.c.config_name.label("config_name"),
            base_rows.c.data_type.label("data_type"),
            base_rows.c.ttl.label("ttl"),
            base_rows.c.row_date.label("row_date"),
            base_rows.c.quantity.label("quantity"),
        )
        .select_from(base_rows)
        .subquery("d")
    )

    stmt = (
        select(
            sub_b.c.country.label("country"),
            sub_b.c.category.label("category"),
            sub_b.c.config_code.label("config_code"),
            sub_b.c.config_name.label("config_name"),
            sub_b.c.data_type.label("data_type"),
            sub_b.c.ttl.label("ttl"),
            sub_a.c.version_date.label("version_date"),
            sub_c.c.period_date.label("period_date"),
            func.coalesce(sub_d.c.quantity, 0).label("quantity"),
        )
        .select_from(sub_a)
        .join(sub_b, sub_b.c.upload_id == sub_a.c.upload_id)
        .join(sub_c, literal(True))  # CROSS JOIN
        .outerjoin(
            sub_d,
            (sub_d.c.upload_id == sub_a.c.upload_id)
            & (sub_d.c.country == sub_b.c.country)
            & (sub_d.c.category == sub_b.c.category)
            & (sub_d.c.config_code == sub_b.c.config_code)
            & (sub_d.c.config_name == sub_b.c.config_name)
            & (sub_d.c.data_type == sub_b.c.data_type)
            & (sub_d.c.ttl == sub_b.c.ttl)
            & (sub_d.c.row_date == sub_c.c.period_date),
        )
        .order_by(
            sub_c.c.period_date,
            sub_b.c.country,
            sub_b.c.category,
            sub_b.c.config_code,
            sub_b.c.config_name,
            sub_a.c.version_date,
        )
    )

    rows = db.execute(stmt).all()

    row_groups_map: dict[tuple, dict] = {}
    period_columns_set: set[str] = set()
    for row in rows:
        key = (
            row.country,
            row.category,
            row.config_code,
            row.config_name,
            row.data_type,
            row.ttl,
            row.version_date,
        )
        entry = row_groups_map.get(key)
        if entry is None:
            entry = {
                "country": row.country,
                "category": row.category,
                "config_code": row.config_code,
                "config_name": row.config_name,
                "data_type": row.data_type,
                "ttl": row.ttl,
                "version_date": row.version_date,
                "quantities": {},
            }
            row_groups_map[key] = entry
        period_str = row.period_date.isoformat() if hasattr(row.period_date, "isoformat") else str(row.period_date)
        entry["quantities"][period_str] = int(row.quantity)
        period_columns_set.add(period_str)

    period_columns = sorted(period_columns_set)
    row_groups = [PivotRow(**entry) for entry in row_groups_map.values()]

    return PivotQueryResponse(
        period_columns=period_columns,
        row_groups=row_groups,
        total_rows=len(row_groups),
        version_dates=list(req.version_dates),
        date_granularity="day" if req.expand_to_daily else "week",
    )


def _query_demand_plus_supply(
    db: Session, req: PivotQueryRequest
) -> PivotQueryResponse:
    """v0.5.7 新模式：b 子查询 GROUP BY 不含 data_type，Python 层产出 4 行/组。

    处理流程（spec §11.3）：
    1. 分组：按 (country, category, config_code, config_name, ttl, version_date) 分组
    2. 拆分：每组按 data_type 拆为 Demand 行 / Supply 行
    3. 兜底：缺失视为 0
    4. 输出 Demand 行 + Supply 行（与 demand 模式同格式）
    5. TTL_GAP[period_date] = Supply.quantity - Demand.quantity；新增一行
    6. Rolling_TTLGAP 累计：首期 = TTL_GAP[0]，后续 = 上期 + TTL_GAP[i]；新增一行
    7. 合并每组 4 行 → row_groups

    参数:
        db: SQLAlchemy Session
        req: 透视查询请求体（pivot_type='demand_plus_supply'，version_dates 已 Pydantic 校验为 1 个）

    返回:
        PivotQueryResponse: 派生字段 TTL_GAP / Rolling_TTLGAP 在响应中实时计算，不入库
    """
    filters = _build_base_rows_filters(req)

    base_rows = (
        select(
            models.DspUploadRow.id.label("row_id"),
            models.DspUploadRow.upload_id.label("upload_id"),
            models.DspUploadRow.country.label("country"),
            models.DspUploadRow.category.label("category"),
            models.DspUploadRow.config_code.label("config_code"),
            models.DspUploadRow.config_name.label("config_name"),
            models.DspUploadRow.data_type.label("data_type"),
            models.DspUploadRow.ttl.label("ttl"),
            models.DspUploadRow.date.label("row_date"),
            models.DspUploadRow.quantity.label("quantity"),
        )
        .join(models.DspUpload, models.DspUploadRow.upload_id == models.DspUpload.id)
        .where(*filters)
        .cte("base_rows")
    )

    sub_a = _build_a_subquery(req)
    sub_c = _build_c_subquery(req)

    # b 子查询：GROUP BY 不含 data_type，让同一业务维度的 Demand / Supply 配对
    sub_b = (
        select(
            base_rows.c.upload_id.label("upload_id"),
            base_rows.c.country.label("country"),
            base_rows.c.category.label("category"),
            base_rows.c.config_code.label("config_code"),
            base_rows.c.config_name.label("config_name"),
            base_rows.c.ttl.label("ttl"),
        )
        .select_from(base_rows)
        .group_by(
            base_rows.c.upload_id,
            base_rows.c.country,
            base_rows.c.category,
            base_rows.c.config_code,
            base_rows.c.config_name,
            base_rows.c.ttl,
        )
        .subquery("b")
    )

    # d 子查询：保留 data_type 字段，供 Python 层区分
    sub_d = (
        select(
            base_rows.c.upload_id.label("upload_id"),
            base_rows.c.country.label("country"),
            base_rows.c.category.label("category"),
            base_rows.c.config_code.label("config_code"),
            base_rows.c.config_name.label("config_name"),
            base_rows.c.data_type.label("data_type"),
            base_rows.c.ttl.label("ttl"),
            base_rows.c.row_date.label("row_date"),
            base_rows.c.quantity.label("quantity"),
        )
        .select_from(base_rows)
        .subquery("d")
    )

    stmt = (
        select(
            sub_b.c.country.label("country"),
            sub_b.c.category.label("category"),
            sub_b.c.config_code.label("config_code"),
            sub_b.c.config_name.label("config_name"),
            sub_b.c.ttl.label("ttl"),
            sub_a.c.version_date.label("version_date"),
            sub_c.c.period_date.label("period_date"),
            sub_d.c.data_type.label("data_type"),
            func.coalesce(sub_d.c.quantity, 0).label("quantity"),
        )
        .select_from(sub_a)
        .join(sub_b, sub_b.c.upload_id == sub_a.c.upload_id)
        .join(sub_c, literal(True))
        .outerjoin(
            sub_d,
            (sub_d.c.upload_id == sub_a.c.upload_id)
            & (sub_d.c.country == sub_b.c.country)
            & (sub_d.c.category == sub_b.c.category)
            & (sub_d.c.config_code == sub_b.c.config_code)
            & (sub_d.c.config_name == sub_b.c.config_name)
            & (sub_d.c.ttl == sub_b.c.ttl)
            & (sub_d.c.row_date == sub_c.c.period_date),
        )
        .order_by(
            sub_c.c.period_date,
            sub_b.c.country,
            sub_b.c.category,
            sub_b.c.config_code,
            sub_b.c.config_name,
            sub_a.c.version_date,
        )
    )

    rows = db.execute(stmt).all()

    # ---------- Python 层后处理（spec §11.3 七步） ----------

    # Step 1+3：先按业务维度 + version_date 聚合到 inner 字典
    # group_key = (country, category, config_code, config_name, ttl, version_date)
    # value = {"Demand": {period: qty}, "Supply": {period: qty}}
    grouped: dict[tuple, dict] = {}
    period_columns_set: set[str] = set()
    for row in rows:
        group_key = (
            row.country,
            row.category,
            row.config_code,
            row.config_name,
            row.ttl,
            row.version_date,
        )
        period_str = (
            row.period_date.isoformat()
            if hasattr(row.period_date, "isoformat")
            else str(row.period_date)
        )
        period_columns_set.add(period_str)
        # 初始化嵌套结构：默认两层都存在，便于后期取默认值
        if group_key not in grouped:
            grouped[group_key] = {"Demand": {}, "Supply": {}}
        bucket = grouped[group_key]
        # data_type 可能为 None（d LEFT JOIN 未命中），忽略：等价 quantity=0
        if row.data_type in ("Demand", "Supply"):
            bucket[row.data_type][period_str] = int(row.quantity)

    period_columns = sorted(period_columns_set)
    row_groups: list[PivotRow] = []

    for group_key in grouped:
        country, category, config_code, config_name, ttl, version_date = group_key
        demand_map = grouped[group_key]["Demand"]
        supply_map = grouped[group_key]["Supply"]

        # Demand 行：缺失期填 0
        demand_q = {p: int(demand_map.get(p, 0)) for p in period_columns}
        # Supply 行
        supply_q = {p: int(supply_map.get(p, 0)) for p in period_columns}

        row_groups.append(
            PivotRow(
                country=country,
                category=category,
                config_code=config_code,
                config_name=config_name,
                data_type="Demand",
                ttl=ttl,
                version_date=version_date,
                quantities=demand_q,
            )
        )
        row_groups.append(
            PivotRow(
                country=country,
                category=category,
                config_code=config_code,
                config_name=config_name,
                data_type="Supply",
                ttl=ttl,
                version_date=version_date,
                quantities=supply_q,
            )
        )

        # TTL_GAP：按 period_date 升序逐期计算
        ttl_gap_map: dict[str, int] = {}
        for p in period_columns:
            ttl_gap_map[p] = supply_q[p] - demand_q[p]
        row_groups.append(
            PivotRow(
                country=country,
                category=category,
                config_code=config_code,
                config_name=config_name,
                data_type="TTL_GAP",
                ttl=ttl,
                version_date=version_date,
                quantities=ttl_gap_map,
            )
        )

        # Rolling_TTLGAP：累计
        rolling_map: dict[str, int] = {}
        acc = 0
        for p in period_columns:
            acc += ttl_gap_map[p]
            rolling_map[p] = acc
        row_groups.append(
            PivotRow(
                country=country,
                category=category,
                config_code=config_code,
                config_name=config_name,
                data_type="Rolling_TTLGAP",
                ttl=ttl,
                version_date=version_date,
                quantities=rolling_map,
            )
        )

    return PivotQueryResponse(
        period_columns=period_columns,
        row_groups=row_groups,
        total_rows=len(row_groups),
        version_dates=list(req.version_dates),
        date_granularity="day" if req.expand_to_daily else "week",
    )


def query_pivot(db: Session, req: PivotQueryRequest) -> PivotQueryResponse:
    """执行透视查询，返回长格式响应。

    模式分发：
    - `pivot_type='demand'`：沿用 §3 主路径
    - `pivot_type='demand_plus_supply'`：进入 §11 路径

    参数:
        db: SQLAlchemy Session
        req: 透视查询请求体（已通过 Pydantic 校验 + 笛卡尔积预检）

    返回:
        PivotQueryResponse

    异常:
        无业务异常；SQLAlchemy 报错时由 FastAPI 映射为 500
    """
    if req.pivot_type == "demand_plus_supply":
        return _query_demand_plus_supply(db, req)
    return _query_demand(db, req)
