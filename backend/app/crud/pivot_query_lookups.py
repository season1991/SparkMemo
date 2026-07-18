"""透视查询辅助 lookup CRUD（v0.5.6）。

本模块提供 4 个只读 lookup 接口，供前端透视查询页面下拉选项使用：
1. `distinct_countries`：返回指定 (vendor+item+sub_item+version_dates) 下所有去重 country。
2. `distinct_categories`：在 countries 基础上返回去重 category。
3. `distinct_config_names`：在 countries + categories 基础上返回去重 config_name。
4. `weeks_of_month`：返回指定 ISO 年 + 自然月的所有 (week_id, week_start_date)。

注：所有 lookup 仅依赖 dsp_uploads / dsp_upload_rows / week_dt 三张表，不修改任何数据。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app import models
from app.schemas import WeekInfo


def _parse_csv(value: Optional[str]) -> list[str]:
    """解析逗号分隔的字符串为 list；空字符串或 None 返回 []。"""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _upload_join_filter(
    vendor: str,
    item: str,
    sub_item: str,
    version_dates: list[str],
):
    """构造 dsp_uploads JOIN dsp_upload_rows 的筛选条件。"""
    return [
        models.DspUploadRow.upload_id == models.DspUpload.id,
        models.DspUpload.vendor == vendor,
        models.DspUpload.item == item,
        models.DspUpload.sub_item == sub_item,
        models.DspUpload.version_date.in_(version_dates),
        models.DspUploadRow.data_type == "Demand",  # v0.5.6 固定
    ]


def distinct_countries(
    db: Session,
    *,
    vendor: str,
    item: str,
    sub_item: str,
    version_dates_csv: Optional[str] = None,
) -> list[str]:
    """返回指定 (vendor+item+sub_item+version_dates) 下所有去重 country。

    参数:
        db: SQLAlchemy Session。
        vendor / item / sub_item: 必填，定位维度。
        version_dates_csv: 逗号分隔的版本日期字符串；空/None 时退化为「不限」。

    返回:
        list[str]: 去重的 country 值，按字母升序。空结果返回 []。
    """
    version_dates = _parse_csv(version_dates_csv)
    stmt = (
        select(distinct(models.DspUploadRow.country))
        .select_from(models.DspUploadRow)
        .join(models.DspUpload, models.DspUploadRow.upload_id == models.DspUpload.id)
        .where(*_upload_join_filter(vendor, item, sub_item, version_dates))
        .where(models.DspUploadRow.country.is_not(None))
        .where(models.DspUploadRow.country != "")
        .order_by(models.DspUploadRow.country)
    )
    return [r[0] for r in db.execute(stmt).all() if r[0]]


def distinct_categories(
    db: Session,
    *,
    vendor: str,
    item: str,
    sub_item: str,
    version_dates_csv: Optional[str] = None,
    countries_csv: Optional[str] = None,
) -> list[str]:
    """返回指定条件下（vendor+item+sub_item+version_dates+countries）去重 category。

    参数:
        countries_csv: 已选 countries（逗号分隔）；空/None 时不限。

    返回:
        list[str]: 去重的 category 值，按字母升序。
    """
    version_dates = _parse_csv(version_dates_csv)
    countries = _parse_csv(countries_csv)
    filters = _upload_join_filter(vendor, item, sub_item, version_dates)
    if countries:
        filters.append(models.DspUploadRow.country.in_(countries))
    stmt = (
        select(distinct(models.DspUploadRow.category))
        .select_from(models.DspUploadRow)
        .join(models.DspUpload, models.DspUploadRow.upload_id == models.DspUpload.id)
        .where(*filters)
        .where(models.DspUploadRow.category.is_not(None))
        .where(models.DspUploadRow.category != "")
        .order_by(models.DspUploadRow.category)
    )
    return [r[0] for r in db.execute(stmt).all() if r[0]]


def distinct_config_names(
    db: Session,
    *,
    vendor: str,
    item: str,
    sub_item: str,
    version_dates_csv: Optional[str] = None,
    countries_csv: Optional[str] = None,
    categories_csv: Optional[str] = None,
) -> list[str]:
    """返回指定条件下（vendor+item+sub_item+version_dates+countries+categories）去重 config_name。"""
    version_dates = _parse_csv(version_dates_csv)
    countries = _parse_csv(countries_csv)
    categories = _parse_csv(categories_csv)
    filters = _upload_join_filter(vendor, item, sub_item, version_dates)
    if countries:
        filters.append(models.DspUploadRow.country.in_(countries))
    if categories:
        filters.append(models.DspUploadRow.category.in_(categories))
    stmt = (
        select(distinct(models.DspUploadRow.config_name))
        .select_from(models.DspUploadRow)
        .join(models.DspUpload, models.DspUploadRow.upload_id == models.DspUpload.id)
        .where(*filters)
        .where(models.DspUploadRow.config_name.is_not(None))
        .where(models.DspUploadRow.config_name != "")
        .order_by(models.DspUploadRow.config_name)
    )
    return [r[0] for r in db.execute(stmt).all() if r[0]]


def weeks_of_month(
    db: Session, *, year: int, month: int
) -> list[WeekInfo]:
    """返回指定 ISO 年 + 自然月的所有 (week_id, week_start_date) 映射。

    参数:
        db: SQLAlchemy Session。
        year: ISO 年（week_id 所属年份）；与 week_dt.year_id 字段对齐。
        month: 自然月（1-12）；与 week_dt.month_id 字段对齐。

    返回:
        list[WeekInfo]: 按 dt 升序排列；空结果返回 []。

    异常:
        ValueError: month 不在 1-12。
    """
    if not (1 <= month <= 12):
        raise ValueError("month must be in 1-12")
    rows = db.execute(
        select(models.WeekDt.week_id, models.WeekDt.dt)
        .where(models.WeekDt.year_id == year)
        .where(models.WeekDt.month_id == month)
        .where(models.WeekDt.is_week_start == True)  # noqa: E712
        .order_by(models.WeekDt.dt)
    ).all()
    return [
        WeekInfo(
            week_id=int(r.week_id),
            week_start_date=r.dt.isoformat() if hasattr(r.dt, "isoformat") else str(r.dt),
        )
        for r in rows
    ]