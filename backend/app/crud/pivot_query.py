"""透视查询 CRUD（v0.5.6）。

设计要点（与 spec §透视查询 章节对齐）：
1. 三子查询拼接：横向（dsp_uploads × dsp_upload_rows 业务行去重）× 纵向（week_dt）× 交叉点（dsp_upload_rows 明细 quantity）。
2. 共享 CTE：b 与 d 子查询都从同一个 `base_rows` CTE 中取，**只扫描一次 dsp_upload_rows**。
3. 笛卡尔积在数据库层通过 SQL JOIN 自然展开，无 GROUP BY 即可获得「每行 × 每日期 = 一条记录」。
4. 数据量保护：`estimate_size()` 在执行前估算 `|b| × |c|`，超出 `MAX_CARTESIAN` 由路由层返回 422。
5. 不依赖 DB 日期函数：所有日期范围在 Python 层构造后作为参数传入。

不抛 4xx HTTPException；业务异常（如 week_dt 表不存在）由调用方按场景映射。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from app import models
from app.schemas import PivotQueryRequest, PivotQueryResponse, PivotRow


# v0.5.6 笛卡尔积硬上限：超出 → 422 拒绝执行
MAX_CARTESIAN = 50000


def _build_base_rows_filters(req: PivotQueryRequest) -> list:
    """构造 base_rows CTE 的筛选条件（b 与 d 共享）。"""
    filters = [
        models.DspUploadRow.upload_id == models.DspUpload.id,
        models.DspUpload.vendor == req.vendor,
        models.DspUpload.item == req.item,
        models.DspUpload.sub_item == req.sub_item,
        models.DspUpload.version_date.in_(req.version_dates),
        models.DspUploadRow.data_type == "Demand",  # v0.5.6 固定
    ]
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
    """估算笛卡尔积规模 `|b| × |c|`，用于数据量保护。

    - `|b|` = 满足条件的 dsp_upload_rows 去重业务行数
      （按 country, category, config_code, config_name, data_type, ttl, upload_id 去重）
    - `|c|` = 满足条件的 week_dt 行数

    参数:
        db: SQLAlchemy Session。
        req: 透视查询请求体（已通过 Pydantic 级联校验）。

    返回:
        int: 笛卡尔积估算行数。`|b| == 0` 或 `|c| == 0` 时直接返回 0。

    异常:
        无业务异常。SQLAlchemy 出错时由 FastAPI 兜底为 500。
    """
    b_filters = _build_base_rows_filters(req)

    # b 去重集合按 7 字段组合，使用 tuple distinct；COUNT(DISTINCT col1, col2, ...)
    # 在 SQLite 与 MySQL 上语法略有差异，这里使用 subquery + distinct + count
    b_sub = (
        select(
            models.DspUploadRow.country,
            models.DspUploadRow.category,
            models.DspUploadRow.config_code,
            models.DspUploadRow.config_name,
            models.DspUploadRow.data_type,
            models.DspUploadRow.ttl,
            models.DspUploadRow.upload_id,
        )
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


def query_pivot(db: Session, req: PivotQueryRequest) -> PivotQueryResponse:
    """执行透视查询，返回长格式响应。

    流程：
    1. 构建 `base_rows` CTE：一次扫描 dsp_upload_rows，含所有 b/d 需要的列
    2. b 子查询：从 CTE 取去重业务行（横向）
    3. d 子查询：从 CTE 取明细（date, quantity，交叉点）
    4. c 子查询：week_dt 按 year/month/week/is_week_start 过滤（纵向）
    5. 主查询：a × b × c LEFT JOIN d，COALESCE 兜底 0
    6. Python 层聚合成 `row_groups`：相同业务维度 + version_date 的行合并为一个对象

    参数:
        db: SQLAlchemy Session。
        req: 透视查询请求体（已通过 Pydantic 级联校验 + 数据量预检）。

    返回:
        PivotQueryResponse: 含 `period_columns` / `row_groups` / `total_rows` / `version_dates` /
        `date_granularity` 的响应。

    异常:
        无业务异常。SQLAlchemy 出错时由 FastAPI 兜底为 500。
    """
    filters = _build_base_rows_filters(req)

    # 1. base_rows CTE
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

    # 2. a 子查询：dsp_uploads（横向批次）
    sub_a = (
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

    # 3. b 子查询：横向业务行（按 7 个业务维度 GROUP BY 去重，**不含 row_id**）
    #    注：DISTINCT 不能用，因为 base_rows 包含 row_id (PK) 会让"不同日期的同一业务行"
    #    被认为是不同行；必须用 GROUP BY 把 row_id 排除。
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

    # 4. d 子查询：从 CTE 取明细（交叉点）：含全部业务维度 + row_date + quantity
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

    # 5. c 子查询：week_dt（纵向）
    c_filters = []
    if req.years:
        c_filters.append(models.WeekDt.year_id.in_(req.years))
    if req.months:
        c_filters.append(models.WeekDt.month_id.in_(req.months))
    if req.weeks:
        c_filters.append(models.WeekDt.week_id.in_(req.weeks))
    if not req.expand_to_daily:
        c_filters.append(models.WeekDt.is_week_start == True)  # noqa: E712

    sub_c = (
        select(models.WeekDt.dt.label("period_date"))
        .where(*c_filters)
        .subquery("c")
    )

    # 6. 主查询：a JOIN b CROSS JOIN c LEFT JOIN d（按业务维度组合 + row_date 关联）
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
        .join(sub_c, literal(True))  # CROSS JOIN：b × c 笛卡尔积
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

    # 7. Python 层聚合成 row_groups
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
        # 强制转字符串：SQLite 中 String 字段可能被推断为 datetime.date，
        # Pydantic 要求 quantities 的 key 是 str
        period_str = row.period_date.isoformat() if hasattr(row.period_date, "isoformat") else str(row.period_date)
        entry["quantities"][period_str] = int(row.quantity)
        period_columns_set.add(period_str)

    period_columns = sorted(period_columns_set)
    row_groups = [
        PivotRow(**entry)
        for entry in row_groups_map.values()
    ]

    return PivotQueryResponse(
        period_columns=period_columns,
        row_groups=row_groups,
        total_rows=len(row_groups),
        version_dates=list(req.version_dates),
        date_granularity="day" if req.expand_to_daily else "week",
    )