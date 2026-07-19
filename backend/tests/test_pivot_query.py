"""透视查询模块测试（v0.5.6）。

测试覆盖：
1. Pydantic 级联校验（业务行 + 时间维度）
2. 笛卡尔积预检（MAX_CARTESIAN）
3. 正常路径（单版本 / 多版本 / 按周 / 按日 / 空数据）
4. COALESCE 兜底（缺失 quantity → 0）
5. 跨数据源 JOIN（dsp_uploads × dsp_upload_rows × week_dt）

注：
- week_dt 是外部表，本测试套件需在 SQLite 中 CREATE TABLE week_dt 后注入数据
- 测试中通过 `make_week_dt` fixture 注入固定日期维度
"""
from __future__ import annotations

from datetime import date as _date

import pytest

from app import models
from app.crud import pivot_query
from app.crud import pivot_query_lookups


# ---------- helpers / fixtures ----------


@pytest.fixture
def make_week_dt():
    """在测试 SQLite 中创建 week_dt 表（外部表）并按需插入数据。

    用法：
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7, week_id=27, is_week_start=True)
        make_week_dt(db, "2026-07-07", year_id=2026, month_id=7, week_id=27, is_week_start=False)
    """
    from sqlalchemy import text

    def _ensure_table(db):
        # 幂等创建 week_dt（SQLite 与 MySQL 兼容）
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS week_dt (
                dt VARCHAR(10) PRIMARY KEY,
                year_id SMALLINT NOT NULL,
                month_id TINYINT NOT NULL,
                week_id TINYINT NOT NULL,
                is_week_start BOOLEAN NOT NULL DEFAULT 0
            )
        """))
        db.commit()

    def factory(db, dt, *, year_id, month_id, week_id, is_week_start=False):
        _ensure_table(db)
        row = models.WeekDt(
            dt=dt,
            year_id=year_id,
            month_id=month_id,
            week_id=week_id,
            is_week_start=is_week_start,
        )
        db.add(row)
        db.commit()
        return row

    return factory


def _make_pivot_fact_rows(country, category, config_code, config_name, data_type, ttl,
                          weekly_quantities: dict[str, int]):
    """把 {row_date: quantity} 展开为 dsp_upload_rows dict 列表。"""
    return [
        {
            "country": country,
            "category": category,
            "config_code": config_code,
            "config_name": config_name,
            "data_type": data_type,
            "ttl": ttl,
            "ym": dt[:7],
            "week": f"WK{week_id}",
            "date": dt,
            "quantity": qty,
        }
        for dt, qty, week_id in weekly_quantities  # weekly_quantities 是 [(dt, qty, week_id), ...]
    ]


# ---------- TC01: Pydantic 级联校验 ----------


class TestCascadeValidation:
    """业务行级联 + 时间维度级联 + 至少一个时间维度。"""

    def test_config_names_without_categories(self):
        from pydantic import ValidationError

        from app.schemas import PivotQueryRequest

        with pytest.raises(ValidationError) as exc_info:
            PivotQueryRequest(
                pivot_type="demand",
                vendor="Arista",
                item="X",
                sub_item="Y",
                version_dates=["2026-06-29"],
                config_names=["32Q-TOR-T3"],
                # 故意不传 categories
                years=[2026],
            )
        assert "categories is required" in str(exc_info.value)

    def test_categories_without_countries(self):
        from pydantic import ValidationError

        from app.schemas import PivotQueryRequest

        with pytest.raises(ValidationError) as exc_info:
            PivotQueryRequest(
                pivot_type="demand",
                vendor="Arista",
                item="X",
                sub_item="Y",
                version_dates=["2026-06-29"],
                categories=["交换机整机"],
                years=[2026],
            )
        assert "countries is required" in str(exc_info.value)

    def test_weeks_without_years(self):
        from pydantic import ValidationError

        from app.schemas import PivotQueryRequest

        with pytest.raises(ValidationError) as exc_info:
            PivotQueryRequest(
                pivot_type="demand",
                vendor="Arista",
                item="X",
                sub_item="Y",
                version_dates=["2026-06-29"],
                weeks=[27],
            )
        assert "years and months are required" in str(exc_info.value)

    def test_months_without_years(self):
        from pydantic import ValidationError

        from app.schemas import PivotQueryRequest

        with pytest.raises(ValidationError) as exc_info:
            PivotQueryRequest(
                pivot_type="demand",
                vendor="Arista",
                item="X",
                sub_item="Y",
                version_dates=["2026-06-29"],
                months=[7],
            )
        assert "years is required" in str(exc_info.value)

    def test_no_time_dimension(self):
        from pydantic import ValidationError

        from app.schemas import PivotQueryRequest

        with pytest.raises(ValidationError) as exc_info:
            PivotQueryRequest(
                pivot_type="demand",
                vendor="Arista",
                item="X",
                sub_item="Y",
                version_dates=["2026-06-29"],
                # 故意不传 years/months/weeks
            )
        assert "at least one of years / months / weeks" in str(exc_info.value)

    def test_valid_full_cascade(self):
        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista",
            item="X",
            sub_item="Y",
            version_dates=["2026-06-29"],
            countries=["爱尔兰"],
            categories=["交换机整机"],
            config_names=["32Q-TOR-T3"],
            years=[2026],
            months=[7],
            weeks=[27],
        )
        assert req.pivot_type == "demand"
        assert req.expand_to_daily is False

    def test_invalid_version_date_format(self):
        from pydantic import ValidationError

        from app.schemas import PivotQueryRequest

        with pytest.raises(ValidationError):
            PivotQueryRequest(
                pivot_type="demand",
                vendor="Arista",
                item="X",
                sub_item="Y",
                version_dates=["2026/06/29"],  # 错误分隔符
                years=[2026],
            )

    def test_invalid_month_range(self):
        from pydantic import ValidationError

        from app.schemas import PivotQueryRequest

        with pytest.raises(ValidationError) as exc_info:
            PivotQueryRequest(
                pivot_type="demand",
                vendor="Arista",
                item="X",
                sub_item="Y",
                version_dates=["2026-06-29"],
                months=[13],  # 超出 1-12
            )
        assert "months must be in 1-12" in str(exc_info.value)


# ---------- TC02: 笛卡尔积预检 ----------


class TestCartesianEstimation:
    """estimate_size 应正确估算 |b| × |c|。"""

    def test_zero_when_no_business_rows(self, db, make_dsp_upload, make_week_dt):
        # 没有 dsp_upload_rows，|b|=0 → 估算=0
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29")
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        assert pivot_query.estimate_size(db, req) == 0

    def test_count_business_rows_and_weeks(self, db, make_dsp_upload, make_week_dt):
        # 1 个 upload，2 个业务行（demand），3 个周起始日 → 估算 = 2 × 3 = 6
        fact_rows = []
        for country in ["爱尔兰", "美国"]:
            fact_rows.append({
                "country": country,
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 10,
            })
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)
        make_week_dt(db, "2026-07-13", year_id=2026, month_id=7,
                     week_id=28, is_week_start=True)
        make_week_dt(db, "2026-07-20", year_id=2026, month_id=7,
                     week_id=29, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        assert pivot_query.estimate_size(db, req) == 6  # 2 × 3

    def test_filter_by_country(self, db, make_dsp_upload, make_week_dt):
        # 5 个不同 country 业务行，筛选 country=爱尔兰 → |b|=1
        fact_rows = []
        for i, country in enumerate(["爱尔兰", "美国", "中国", "日本", "英国"]):
            fact_rows.append({
                "country": country,
                "category": "交换机整机",
                "config_code": f"X{i:03d}",
                "config_name": f"32Q-TOR-T{i}",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 10,
            })
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            countries=["爱尔兰"],
            years=[2026],
        )
        assert pivot_query.estimate_size(db, req) == 1


# ---------- TC03: API 预检失败 ----------


class TestApiEstimationGuard:
    """API 层应在校验失败时返回 422。"""

    @pytest.mark.asyncio
    async def test_cartesian_exceeds_limit(self, client, db, monkeypatch):
        # 通过 monkeypatch 让 estimate_size 返回极大值，强制触发预检
        def _huge_estimate(*args, **kwargs):
            return 999999

        monkeypatch.setattr(pivot_query, "estimate_size", _huge_estimate)

        payload = {
            "pivot_type": "demand",
            "vendor": "Arista",
            "item": "X",
            "sub_item": "Y",
            "version_dates": ["2026-06-29"],
            "years": [2026],
        }
        resp = await client.post("/api/pivot-query", json=payload)
        assert resp.status_code == 422
        assert "cartesian product" in resp.json()["detail"]


# ---------- TC04: 正常路径 ----------


class TestNormalPath:
    """query_pivot 应正确执行透视并返回长格式响应。"""

    def test_single_version_single_business_row(
        self, db, make_dsp_upload, make_week_dt
    ):
        # 1 个 upload，1 个业务行（Demand），3 个周起始日
        fact_rows = [
            {
                "country": "爱尔兰",
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 100,
            },
            {
                "country": "爱尔兰",
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK28",
                "date": "2026-07-13",
                "quantity": 50,
            },
            {
                "country": "爱尔兰",
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK29",
                "date": "2026-07-20",
                "quantity": 75,
            },
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)
        make_week_dt(db, "2026-07-13", year_id=2026, month_id=7,
                     week_id=28, is_week_start=True)
        make_week_dt(db, "2026-07-20", year_id=2026, month_id=7,
                     week_id=29, is_week_start=True)
        # 添加第 4 个周起始日，验证 COALESCE 兜底
        make_week_dt(db, "2026-07-27", year_id=2026, month_id=7,
                     week_id=30, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)

        assert result.date_granularity == "week"
        assert result.total_rows == 1
        assert result.period_columns == ["2026-07-06", "2026-07-13",
                                         "2026-07-20", "2026-07-27"]
        assert len(result.row_groups) == 1
        row = result.row_groups[0]
        assert row.country == "爱尔兰"
        assert row.category == "交换机整机"
        assert row.config_name == "32Q-TOR-T3"
        assert row.data_type == "Demand"
        assert row.ttl == 4
        assert row.version_date == "2026-06-29"
        assert row.quantities == {
            "2026-07-06": 100,
            "2026-07-13": 50,
            "2026-07-20": 75,
            "2026-07-27": 0,  # COALESCE 兜底
        }

    def test_expand_to_daily(self, db, make_dsp_upload, make_week_dt):
        # expand_to_daily=True 时去掉 is_week_start 过滤，每天都展开
        fact_rows = [
            {
                "country": "爱尔兰",
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 70,  # 周一至周日每天 10
            },
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        # 7 天：周一到周日
        for i in range(7):
            from datetime import timedelta
            dt = (_date(2026, 7, 6) + timedelta(days=i)).isoformat()
            make_week_dt(db, dt, year_id=2026, month_id=7,
                         week_id=27, is_week_start=(i == 0))

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
            expand_to_daily=True,
        )
        result = pivot_query.query_pivot(db, req)
        assert result.date_granularity == "day"
        assert result.period_columns == [
            "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09",
            "2026-07-10", "2026-07-11", "2026-07-12",
        ]
        row = result.row_groups[0]
        # 只有 2026-07-06 有数据，其它天都是 0（COALESCE）
        assert row.quantities["2026-07-06"] == 70
        for dt in result.period_columns[1:]:
            assert row.quantities[dt] == 0

    def test_multiple_versions(self, db, make_dsp_upload, make_week_dt):
        # 2 个 version_date，每个各有自己的 quantity
        for i, (vd, qty) in enumerate([("2026-06-29", 100), ("2026-07-15", 200)]):
            fact_rows = [
                {
                    "country": "爱尔兰",
                    "category": "交换机整机",
                    "config_code": "X123",
                    "config_name": "32Q-TOR-T3",
                    "data_type": "Demand",
                    "ttl": 4,
                    "ym": "2026-07",
                    "week": "WK27",
                    "date": "2026-07-06",
                    "quantity": qty,
                },
            ]
            make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                            version_date=vd, fact_rows=fact_rows)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29", "2026-07-15"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)

        # 2 个 version_date，每个 1 行 = 2 row_groups
        assert result.total_rows == 2
        assert len(result.row_groups) == 2
        version_dates_returned = {r.version_date for r in result.row_groups}
        assert version_dates_returned == {"2026-06-29", "2026-07-15"}

    def test_supply_rows_excluded(self, db, make_dsp_upload, make_week_dt):
        # Supply 行应被排除（pivot_type=demand 固定 data_type='Demand'）
        fact_rows = [
            {
                "country": "爱尔兰",
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 100,
            },
            {
                "country": "爱尔兰",
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Supply",  # Supply 行
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 999,  # 不应出现在结果中
            },
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        assert result.total_rows == 1
        assert result.row_groups[0].data_type == "Demand"
        assert result.row_groups[0].quantities["2026-07-06"] == 100

    def test_empty_data(self, db, make_dsp_upload, make_week_dt):
        # version_date 不存在 → 空 row_groups
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29")
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        assert result.total_rows == 0
        assert result.row_groups == []

    def test_filter_by_country(self, db, make_dsp_upload, make_week_dt):
        # 多个 country 写入同一 batch（不同行），仅查询 爱尔兰
        fact_rows = []
        for country, qty in [("爱尔兰", 100), ("美国", 200), ("中国", 300)]:
            fact_rows.append({
                "country": country,
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": qty,
            })
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            countries=["爱尔兰"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        assert result.total_rows == 1
        assert result.row_groups[0].country == "爱尔兰"
        assert result.row_groups[0].quantities["2026-07-06"] == 100


# ---------- TC05: API 端到端 ----------


class TestApiEndpoint:
    """端到端 API 调用。"""

    @pytest.mark.asyncio
    async def test_basic_request(self, client, db, make_dsp_upload, make_week_dt):
        fact_rows = [
            {
                "country": "爱尔兰",
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 100,
            },
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        payload = {
            "pivot_type": "demand",
            "vendor": "Arista",
            "item": "X",
            "sub_item": "Y",
            "version_dates": ["2026-06-29"],
            "years": [2026],
        }
        resp = await client.post("/api/pivot-query", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_rows"] == 1
        assert body["period_columns"] == ["2026-07-06"]
        assert body["date_granularity"] == "week"
        assert body["row_groups"][0]["country"] == "爱尔兰"

    @pytest.mark.asyncio
    async def test_cascade_validation_422(self, client):
        # 传 config_names 不传 categories → 422
        payload = {
            "pivot_type": "demand",
            "vendor": "Arista",
            "item": "X",
            "sub_item": "Y",
            "version_dates": ["2026-06-29"],
            "config_names": ["32Q-TOR-T3"],
            "years": [2026],
        }
        resp = await client.post("/api/pivot-query", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_no_time_dimension_422(self, client):
        payload = {
            "pivot_type": "demand",
            "vendor": "Arista",
            "item": "X",
            "sub_item": "Y",
            "version_dates": ["2026-06-29"],
        }
        resp = await client.post("/api/pivot-query", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_cartesian_exceeds_422(self, client, db, make_dsp_upload,
                                          make_week_dt, monkeypatch):
        # 强制 MAX_CARTESIAN=5，构造超大数据集
        monkeypatch.setattr(pivot_query, "MAX_CARTESIAN", 5)

        fact_rows = []
        for i in range(10):
            fact_rows.append({
                "country": f"country_{i}",
                "category": "交换机整机",
                "config_code": f"X{i:03d}",
                "config_name": f"cfg_{i}",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 1,
            })
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        payload = {
            "pivot_type": "demand",
            "vendor": "Arista",
            "item": "X",
            "sub_item": "Y",
            "version_dates": ["2026-06-29"],
            "years": [2026],
        }
        resp = await client.post("/api/pivot-query", json=payload)
        assert resp.status_code == 422
        assert "cartesian product" in resp.json()["detail"]


# ---------- TC06: 辅助 lookup 端点 ----------


class TestLookupEndpoints:
    """透视查询辅助 lookup：业务行级联 + 周编号。"""

    def test_distinct_countries(
        self, db, make_dsp_upload, make_week_dt
    ):
        fact_rows = []
        for country in ["爱尔兰", "美国", "中国", "爱尔兰"]:  # 爱尔兰重复
            fact_rows.append({
                "country": country,
                "category": "交换机整机",
                "config_code": "X123",
                "config_name": "32Q-TOR-T3",
                "data_type": "Demand",
                "ttl": 4,
                "ym": "2026-07",
                "week": "WK27",
                "date": "2026-07-06",
                "quantity": 10,
            })
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        result = pivot_query_lookups.distinct_countries(
            db, vendor="Arista", item="X", sub_item="Y",
            version_dates_csv="2026-06-29",
        )
        # 去重 + 升序
        assert result == ["中国", "爱尔兰", "美国"]

    def test_distinct_countries_excludes_supply(
        self, db, make_dsp_upload, make_week_dt
    ):
        fact_rows = [
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Demand", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 10,
            },
            {
                "country": "德国", "category": "交换机整机",  # Supply 行
                "config_code": "X456", "config_name": "X-Power",
                "data_type": "Supply", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 20,
            },
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        result = pivot_query_lookups.distinct_countries(
            db, vendor="Arista", item="X", sub_item="Y",
            version_dates_csv="2026-06-29",
        )
        # Supply 行被排除
        assert result == ["爱尔兰"]

    def test_distinct_categories_filtered_by_countries(
        self, db, make_dsp_upload, make_week_dt
    ):
        fact_rows = [
            {"country": "爱尔兰", "category": "交换机整机", "config_code": "X1",
             "config_name": "cfg1", "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
             "quantity": 1},
            {"country": "爱尔兰", "category": "路由器", "config_code": "X2",
             "config_name": "cfg2", "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
             "quantity": 1},
            {"country": "美国", "category": "防火墙", "config_code": "X3",
             "config_name": "cfg3", "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
             "quantity": 1},
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        # 不传 countries → 返回全部
        all_cats = pivot_query_lookups.distinct_categories(
            db, vendor="Arista", item="X", sub_item="Y",
            version_dates_csv="2026-06-29",
        )
        assert set(all_cats) == {"交换机整机", "路由器", "防火墙"}
        # 传 countries=爱尔兰 → 只返回爱尔兰下
        filtered = pivot_query_lookups.distinct_categories(
            db, vendor="Arista", item="X", sub_item="Y",
            version_dates_csv="2026-06-29",
            countries_csv="爱尔兰",
        )
        assert set(filtered) == {"交换机整机", "路由器"}

    def test_distinct_config_names_filtered_by_countries_and_categories(
        self, db, make_dsp_upload, make_week_dt
    ):
        fact_rows = [
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X1", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
             "quantity": 1},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X2", "config_name": "64Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
             "quantity": 1},
            {"country": "爱尔兰", "category": "路由器",
             "config_code": "X3", "config_name": "Router-A",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
             "quantity": 1},
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        # 不传 → 返回全部
        all_cfgs = pivot_query_lookups.distinct_config_names(
            db, vendor="Arista", item="X", sub_item="Y",
            version_dates_csv="2026-06-29",
        )
        assert set(all_cfgs) == {"32Q-TOR-T3", "64Q-TOR-T3", "Router-A"}
        # 传 countries + categories → 只返回过滤后的
        filtered = pivot_query_lookups.distinct_config_names(
            db, vendor="Arista", item="X", sub_item="Y",
            version_dates_csv="2026-06-29",
            countries_csv="爱尔兰",
            categories_csv="交换机整机",
        )
        assert set(filtered) == {"32Q-TOR-T3", "64Q-TOR-T3"}

    def test_weeks_of_month(
        self, db, make_week_dt
    ):
        # 2025 年 1 月份的几个周一
        make_week_dt(db, "2025-01-06", year_id=2025, month_id=1,
                     week_id=2, is_week_start=True)
        make_week_dt(db, "2025-01-13", year_id=2025, month_id=1,
                     week_id=3, is_week_start=True)
        make_week_dt(db, "2025-01-20", year_id=2025, month_id=1,
                     week_id=4, is_week_start=True)
        make_week_dt(db, "2025-01-27", year_id=2025, month_id=1,
                     week_id=5, is_week_start=True)
        # 不属于 2025 年 1 月：year_id=2025 但 month_id=12（W01）
        make_week_dt(db, "2024-12-30", year_id=2025, month_id=12,
                     week_id=1, is_week_start=True)
        # 不属于 year_id=2025：month_id=1 但 year_id=2026
        make_week_dt(db, "2026-01-05", year_id=2026, month_id=1,
                     week_id=1, is_week_start=True)
        # 同月但非周起始日：被过滤
        make_week_dt(db, "2025-01-07", year_id=2025, month_id=1,
                     week_id=2, is_week_start=False)

        result = pivot_query_lookups.weeks_of_month(db, year=2025, month=1)
        # 应只返回 4 条（按 dt 升序）
        assert len(result) == 4
        assert [(r.week_id, r.week_start_date) for r in result] == [
            (2, "2025-01-06"),
            (3, "2025-01-13"),
            (4, "2025-01-20"),
            (5, "2025-01-27"),
        ]

    def test_weeks_of_month_invalid_month(self, db):
        import pytest as _pytest
        with _pytest.raises(ValueError):
            pivot_query_lookups.weeks_of_month(db, year=2025, month=13)


class TestLookupApi:
    """API 层 lookup 端点端到端。"""

    @pytest.mark.asyncio
    async def test_get_countries(
        self, client, db, make_dsp_upload, make_week_dt
    ):
        fact_rows = [
            {"country": "爱尔兰", "category": "cat", "config_code": "X",
             "config_name": "n", "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
             "quantity": 1},
        ]
        make_dsp_upload(db, vendor="A", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)

        resp = await client.get(
            "/api/pivot-query/lookups/countries",
            params={"vendor": "A", "item": "X", "sub_item": "Y",
                    "version_dates": "2026-06-29"},
        )
        assert resp.status_code == 200
        assert resp.json() == ["爱尔兰"]

    @pytest.mark.asyncio
    async def test_get_weeks_of_month(
        self, client, db, make_week_dt
    ):
        make_week_dt(db, "2025-01-06", year_id=2025, month_id=1,
                     week_id=2, is_week_start=True)
        resp = await client.get(
            "/api/pivot-query/lookups/weeks-of-month",
            params={"year": 2025, "month": 1},
        )
        assert resp.status_code == 200
        assert resp.json() == [
            {"week_id": 2, "week_start_date": "2025-01-06"}
        ]

    @pytest.mark.asyncio
    async def test_get_weeks_of_month_invalid(
        self, client, db
    ):
        # FastAPI Query(ge=1, le=12) 校验先于函数体；返回 422
        resp = await client.get(
            "/api/pivot-query/lookups/weeks-of-month",
            params={"year": 2025, "month": 13},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_weeks_of_month_missing_param(
        self, client, db
    ):
        # ȱ month  FastAPI Уʧ  422
        resp = await client.get(
            "/api/pivot-query/lookups/weeks-of-month",
            params={"year": 2025},
        )
        assert resp.status_code == 422


# ---------- TC07 (v0.5.7): demand_plus_supply 模式 ----------


class TestDemandPlusSupply:
    """v0.5.7 新增：pivot_type='demand_plus_supply' 模式。

    业务规则（详见 spec §11）：
    1. `version_dates` 仅允许 1 个（单选），违反 → Pydantic 422
    2. SQL `base_rows` CTE 改为 `data_type IN ('Demand', 'Supply')`
    3. `b` 子查询 GROUP BY 去掉 `data_type`，让 Demand/Supply 配对到同一业务组
    4. Python 层后处理产出 4 行/组：Demand / Supply / TTL_GAP / Rolling_TTLGAP
    5. TTL_GAP[period_date] = Supply.quantity - Demand.quantity（缺失视为 0）
    6. Rolling_TTLGAP 累计：首期 = TTL_GAP[0]，后续 = 上期 + TTL_GAP[i]
    """

    # ---- TC07-1: multi version_dates 422 ----
    @pytest.mark.asyncio
    async def test_demand_plus_supply_422_multi_versions(self, client):
        """pivot_type='demand_plus_supply' 不允许多 version_dates。"""
        payload = {
            "pivot_type": "demand_plus_supply",
            "vendor": "Arista",
            "item": "X",
            "sub_item": "Y",
            "version_dates": ["2026-06-29", "2026-07-15"],
            "years": [2026],
        }
        resp = await client.post("/api/pivot-query", json=payload)
        assert resp.status_code == 422

    def test_demand_plus_supply_multi_versions_pydantic(self):
        """同上的 Pydantic 模型层校验（不依赖 API）。"""
        from pydantic import ValidationError

        from app.schemas import PivotQueryRequest

        with pytest.raises(ValidationError) as exc_info:
            PivotQueryRequest(
                pivot_type="demand_plus_supply",
                vendor="Arista",
                item="X",
                sub_item="Y",
                version_dates=["2026-06-29", "2026-07-15"],
                years=[2026],
            )
        assert (
            "demand_plus_supply" in str(exc_info.value).lower()
            or "single" in str(exc_info.value).lower()
            or "1" in str(exc_info.value)
        )

    # ---- TC07-2: 基本 4 行产出 ----
    def test_demand_plus_supply_basic_4_rows(
        self, db, make_dsp_upload, make_week_dt
    ):
        """1 组业务维度 + Demand/Supply 双数据 → row_groups 恰好 4 行。"""
        fact_rows = [
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Demand", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 100,
            },
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Supply", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 120,
            },
        ]
        make_dsp_upload(
            db, vendor="Arista", item="X", sub_item="Y",
            version_date="2026-06-29", fact_rows=fact_rows,
        )
        make_week_dt(
            db, "2026-07-06", year_id=2026, month_id=7,
            week_id=27, is_week_start=True,
        )

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand_plus_supply",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        assert result.total_rows == 4
        assert len(result.row_groups) == 4
        types = [r.data_type for r in result.row_groups]
        assert types == ["Demand", "Supply", "TTL_GAP", "Rolling_TTLGAP"]
        # TTL_GAP = Supply - Demand = 120 - 100 = 20
        ttl_gap = next(r for r in result.row_groups if r.data_type == "TTL_GAP")
        assert ttl_gap.quantities == {"2026-07-06": 20}
        # Rolling_TTLGAP 首期 = TTL_GAP[0] = 20
        rolling = next(
            r for r in result.row_groups if r.data_type == "Rolling_TTLGAP"
        )
        assert rolling.quantities == {"2026-07-06": 20}

    # ---- TC07-3: 缺 Supply → TTL_GAP = 0 - Demand ----
    def test_demand_plus_supply_missing_supply_treated_as_zero(
        self, db, make_dsp_upload, make_week_dt
    ):
        """只有 Demand 没有 Supply → Supply 量按 0，TTL_GAP = -Demand。"""
        fact_rows = [
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Demand", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 100,
            },
        ]
        make_dsp_upload(
            db, vendor="Arista", item="X", sub_item="Y",
            version_date="2026-06-29", fact_rows=fact_rows,
        )
        make_week_dt(
            db, "2026-07-06", year_id=2026, month_id=7,
            week_id=27, is_week_start=True,
        )

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand_plus_supply",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        assert result.total_rows == 4
        demand_row = next(r for r in result.row_groups if r.data_type == "Demand")
        supply_row = next(r for r in result.row_groups if r.data_type == "Supply")
        ttl_gap = next(r for r in result.row_groups if r.data_type == "TTL_GAP")
        assert demand_row.quantities == {"2026-07-06": 100}
        assert supply_row.quantities == {"2026-07-06": 0}
        # TTL_GAP = Supply - Demand = 0 - 100 = -100
        assert ttl_gap.quantities == {"2026-07-06": -100}

    # ---- TC07-4: 缺 Demand → TTL_GAP = Supply ----
    def test_demand_plus_supply_missing_demand_treated_as_zero(
        self, db, make_dsp_upload, make_week_dt
    ):
        """只有 Supply 没有 Demand → Demand 量按 0，TTL_GAP = Supply。"""
        fact_rows = [
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Supply", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 80,
            },
        ]
        make_dsp_upload(
            db, vendor="Arista", item="X", sub_item="Y",
            version_date="2026-06-29", fact_rows=fact_rows,
        )
        make_week_dt(
            db, "2026-07-06", year_id=2026, month_id=7,
            week_id=27, is_week_start=True,
        )

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand_plus_supply",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        demand_row = next(r for r in result.row_groups if r.data_type == "Demand")
        ttl_gap = next(r for r in result.row_groups if r.data_type == "TTL_GAP")
        rolling = next(
            r for r in result.row_groups if r.data_type == "Rolling_TTLGAP"
        )
        assert demand_row.quantities == {"2026-07-06": 0}
        assert ttl_gap.quantities == {"2026-07-06": 80}
        assert rolling.quantities == {"2026-07-06": 80}

    # ---- TC07-5: 多日期 Rolling_TTLGAP 累计 ----
    def test_demand_plus_supply_rolling_ttlgap_cumulative(
        self, db, make_dsp_upload, make_week_dt
    ):
        """3 个周起始日的 Rolling_TTLGAP 累计：首期 = TTL_GAP[0]，后续累计。"""
        # D: 100 / 80 / 50，S: 120 / 90 / 60 → TTL_GAP: 20 / 10 / 10 → Rolling: 20 / 30 / 40
        fact_rows = []
        demand_seq = [("2026-07-06", 100), ("2026-07-13", 80), ("2026-07-20", 50)]
        supply_seq = [("2026-07-06", 120), ("2026-07-13", 90), ("2026-07-20", 60)]
        for dt, q in demand_seq:
            fact_rows.append({
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Demand", "ttl": 4,
                "ym": dt[:7], "week": "WK", "date": dt, "quantity": q,
            })
        for dt, q in supply_seq:
            fact_rows.append({
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Supply", "ttl": 4,
                "ym": dt[:7], "week": "WK", "date": dt, "quantity": q,
            })
        make_dsp_upload(
            db, vendor="Arista", item="X", sub_item="Y",
            version_date="2026-06-29", fact_rows=fact_rows,
        )
        for dt, week_id in [
            ("2026-07-06", 27), ("2026-07-13", 28), ("2026-07-20", 29),
        ]:
            make_week_dt(
                db, dt, year_id=2026, month_id=7,
                week_id=week_id, is_week_start=True,
            )

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand_plus_supply",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        # period_columns 按日期升序
        assert result.period_columns == ["2026-07-06", "2026-07-13", "2026-07-20"]
        # 业务维度按 (country, category, code, name, ttl, version_date) 分组，
        # 且 1 组仅 1 个 version_date，所以 4 行
        assert result.total_rows == 4
        ttl_gap = next(r for r in result.row_groups if r.data_type == "TTL_GAP")
        rolling = next(
            r for r in result.row_groups if r.data_type == "Rolling_TTLGAP"
        )
        assert ttl_gap.quantities == {
            "2026-07-06": 20, "2026-07-13": 10, "2026-07-20": 10,
        }
        assert rolling.quantities == {
            "2026-07-06": 20, "2026-07-13": 30, "2026-07-20": 40,
        }
        # period_columns 必须在每个 row 都覆盖到
        demand_row = next(r for r in result.row_groups if r.data_type == "Demand")
        supply_row = next(r for r in result.row_groups if r.data_type == "Supply")
        assert demand_row.quantities == {
            "2026-07-06": 100, "2026-07-13": 80, "2026-07-20": 50,
        }
        assert supply_row.quantities == {
            "2026-07-06": 120, "2026-07-13": 90, "2026-07-20": 60,
        }

    # ---- TC07-6: demand 模式回归（防回归） ----
    def test_demand_mode_unchanged_by_demand_plus_supply_branch(
        self, db, make_dsp_upload, make_week_dt
    ):
        """需求回归：demand 模式仍只输出 1 行 Demand；不出现 Supply / TTL_GAP。"""
        fact_rows = [
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Demand", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 100,
            },
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Supply", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 999,  # 混入 Supply，demand 模式应忽略
            },
        ]
        make_dsp_upload(
            db, vendor="Arista", item="X", sub_item="Y",
            version_date="2026-06-29", fact_rows=fact_rows,
        )
        make_week_dt(
            db, "2026-07-06", year_id=2026, month_id=7,
            week_id=27, is_week_start=True,
        )

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        assert result.total_rows == 1
        assert result.row_groups[0].data_type == "Demand"
        assert result.row_groups[0].quantities == {"2026-07-06": 100}

    # ---- TC07-7: 不同 ttl 合 1 组（v0.5.7.4） ----
    def test_demand_plus_supply_merge_diff_ttl(
        self, db, make_dsp_upload, make_week_dt
    ):
        """v0.5.7.4：同 (country, cat, code, name, version_date) 下 ttl=100 与 ttl=NULL 应合并为 1 组。

        根因：用户 db 中同一业务维度有 ttl=100 的 Demand 行 + ttl=NULL 的 Supply 行；
        v0.5.7 旧版 group_key 含 ttl 会拆为 2 组 → 8 行（第二组全 0 兜底）；
        v0.5.7.4 修订后 group_key 去 ttl → 合并为 1 组 → 4 行。
        """
        fact_rows = [
            # ttl=100 Demand
            {
                "country": "马来西亚", "category": "交换机整机",
                "config_code": "X123", "config_name": "8Q-TOR-T4",
                "data_type": "Demand", "ttl": 100,
                "ym": "2026-06", "week": "WK26", "date": "2026-06-29",
                "quantity": 100,
            },
            # ttl=NULL Supply（ttl 在 dict 中为 None；make_dsp_upload 按原字段入库）
            {
                "country": "马来西亚", "category": "交换机整机",
                "config_code": "X123", "config_name": "8Q-TOR-T4",
                "data_type": "Supply", "ttl": None,
                "ym": "2026-06", "week": "WK26", "date": "2026-06-29",
                "quantity": 90,
            },
        ]
        make_dsp_upload(
            db, vendor="Arista", item="X", sub_item="Y",
            version_date="2026-06-29", fact_rows=fact_rows,
        )
        make_week_dt(
            db, "2026-06-29", year_id=2026, month_id=6,
            week_id=26, is_week_start=True,
        )

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand_plus_supply",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
        )
        result = pivot_query.query_pivot(db, req)
        # 合并为 1 组 4 行（不是 8 行）
        assert result.total_rows == 4
        assert len(result.row_groups) == 4
        types = [r.data_type for r in result.row_groups]
        assert types == ["Demand", "Supply", "TTL_GAP", "Rolling_TTLGAP"]
        # TTL 展示值：COALESCE(MAX(ttl), 0) = 100（MAX 取最大）
        demand_row = next(r for r in result.row_groups if r.data_type == "Demand")
        supply_row = next(r for r in result.row_groups if r.data_type == "Supply")
        assert demand_row.ttl == 100
        assert supply_row.ttl == 100
        # Demand qty=100, Supply qty=90 → TTL_GAP = 90 - 100 = -10
        ttl_gap = next(r for r in result.row_groups if r.data_type == "TTL_GAP")
        rolling = next(r for r in result.row_groups if r.data_type == "Rolling_TTLGAP")
        assert demand_row.quantities == {"2026-06-29": 100}
        assert supply_row.quantities == {"2026-06-29": 90}
        assert ttl_gap.quantities == {"2026-06-29": -10}
        assert rolling.quantities == {"2026-06-29": -10}

    @pytest.mark.asyncio
    async def test_demand_plus_supply_api_basic(
        self, client, db, make_dsp_upload, make_week_dt
    ):
        """API 端到端：demand_plus_supply 模式返回 4 行 / TTL_GAP 字段为 Supply-Demand。"""
        fact_rows = [
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Demand", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 100,
            },
            {
                "country": "爱尔兰", "category": "交换机整机",
                "config_code": "X123", "config_name": "32Q-TOR-T3",
                "data_type": "Supply", "ttl": 4,
                "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
                "quantity": 130,
            },
        ]
        make_dsp_upload(
            db, vendor="Arista", item="X", sub_item="Y",
            version_date="2026-06-29", fact_rows=fact_rows,
        )
        make_week_dt(
            db, "2026-07-06", year_id=2026, month_id=7,
            week_id=27, is_week_start=True,
        )

        payload = {
            "pivot_type": "demand_plus_supply",
            "vendor": "Arista", "item": "X", "sub_item": "Y",
            "version_dates": ["2026-06-29"],
            "years": [2026],
        }
        resp = await client.post("/api/pivot-query", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_rows"] == 4
        types = [rg["data_type"] for rg in body["row_groups"]]
        assert types == ["Demand", "Supply", "TTL_GAP", "Rolling_TTLGAP"]
        ttl_gap = next(rg for rg in body["row_groups"] if rg["data_type"] == "TTL_GAP")
        assert ttl_gap["quantities"] == {"2026-07-06": 30}


# ---------- TC08 (v0.5.9): Demand 跨版本 diff 过滤 (query_diff) ----------


def _make_two_versions_facts(
    v1_qty, v2_qty, *,
    country="爱尔兰", category="交换机整机",
    config_code="X123", config_name="32Q-TOR-T3",
    dates=("2026-07-06", "2026-07-13", "2026-07-20"),
    week_ids=(27, 28, 29),
):
    """构造 2 个 version_date × N 个周起始日的事实行（quantity 各版本独立同值）。

    返回 (facts_v1, facts_v2)：每边 dict 列表，dsp_uploads 批量入库即可。
    """
    def _row(qty, dt, wk):
        return {
            "country": country, "category": category,
            "config_code": config_code, "config_name": config_name,
            "data_type": "Demand", "ttl": 4,
            "ym": dt[:7], "week": f"WK{wk}", "date": dt,
            "quantity": qty,
        }
    return (
        [_row(v1_qty, dt, wk) for dt, wk in zip(dates, week_ids)],
        [_row(v2_qty, dt, wk) for dt, wk in zip(dates, week_ids)],
    )


def _make_week_dt_range(db, factory, dates, week_ids):
    """注入一组周起始日到 week_dt（仅 is_week_start）。"""
    for dt, wk in zip(dates, week_ids):
        factory(db, dt, year_id=int(dt[:4]), month_id=int(dt[5:7]),
                week_id=wk, is_week_start=True)


class TestQueryDiffFilter:
    """`query_diff=True` 跨多 version_date 后处理：只保留有差异的 period_date。

    见 spec `backend/spec/weekly_demand.md` §12。
    """

    # ---- #1 ----

    def test_query_diff_default_true_single_version(
        self, db, make_dsp_upload, make_week_dt
    ):
        """默认 `query_diff=True` + 单版本：函数内部判定 → 跳过过滤，baseline 不变。"""
        fact_rows = [{
            "country": "爱尔兰", "category": "交换机整机",
            "config_code": "X123", "config_name": "32Q-TOR-T3",
            "data_type": "Demand", "ttl": 4,
            "ym": "2026-07", "week": "WK27", "date": "2026-07-06",
            "quantity": 100,
        }]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=fact_rows)
        _make_week_dt_range(
            db, make_week_dt,
            ("2026-07-06", "2026-07-13", "2026-07-20"),
            (27, 28, 29),
        )

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
            # query_diff 字段未显式提供 → 默认 True
        )
        assert req.query_diff is True

        result = pivot_query.query_pivot(db, req)
        # 单版本无对比对象 → baseline 全保留（含 COALESCE 兜底的 0）
        assert result.period_columns == ["2026-07-06", "2026-07-13", "2026-07-20"]
        assert result.total_rows == 1
        assert result.row_groups[0].quantities == {
            "2026-07-06": 100,
            "2026-07-13": 0,
            "2026-07-20": 0,
        }

    # ---- #2 ----

    def test_query_diff_false_keeps_baseline(
        self, db, make_dsp_upload, make_week_dt
    ):
        """`query_diff=False` + 多版本 → v0.5.7 baseline：所有日期保留、原值。"""
        facts_v1, facts_v2 = _make_two_versions_facts(100, 200)
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-15", fact_rows=facts_v1)
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=facts_v2)
        _make_week_dt_range(db, make_week_dt,
                            ("2026-07-06", "2026-07-13", "2026-07-20"),
                            (27, 28, 29))

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-15", "2026-06-29"],
            years=[2026],
            query_diff=False,
        )
        result = pivot_query.query_pivot(db, req)
        assert result.period_columns == ["2026-07-06", "2026-07-13", "2026-07-20"]
        assert result.total_rows == 2
        for r in result.row_groups:
            assert r.quantities == {
                "2026-07-06": 100 if r.version_date == "2026-06-15" else 200,
                "2026-07-13": 100 if r.version_date == "2026-06-15" else 200,
                "2026-07-20": 100 if r.version_date == "2026-06-15" else 200,
            }

    # ---- #3 ----

    def test_query_diff_strict_equal_drops_date(
        self, db, make_dsp_upload, make_week_dt
    ):
        """`query_diff=True` + 2 版本 + 某日期两版 quantity 相同 → 该日期剪除。"""
        # v1: [10, 20, 30], v2: [10, 99, 30] → 仅 07-13 有差异
        facts_v1 = [
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 10},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK28", "date": "2026-07-13", "quantity": 20},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK29", "date": "2026-07-20", "quantity": 30},
        ]
        facts_v2 = [
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 10},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK28", "date": "2026-07-13", "quantity": 99},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK29", "date": "2026-07-20", "quantity": 30},
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-15", fact_rows=facts_v1)
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=facts_v2)
        _make_week_dt_range(db, make_week_dt,
                            ("2026-07-06", "2026-07-13", "2026-07-20"),
                            (27, 28, 29))

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-15", "2026-06-29"],
            years=[2026],
            query_diff=True,
        )
        result = pivot_query.query_pivot(db, req)
        # 07-06 全等剪除；07-13 差异保留；07-20 全等剪除
        assert result.period_columns == ["2026-07-13"]
        assert result.total_rows == 2
        for r in result.row_groups:
            assert r.quantities == {
                "2026-07-13": 20 if r.version_date == "2026-06-15" else 99,
            }

    # ---- #4 ----

    def test_query_diff_partial_diff_keeps_date(
        self, db, make_dsp_upload, make_week_dt
    ):
        """3 个日期中 2 个有差异、1 个全等 → 保留 2 个差异日期；quantity 为原值（非 delta）。"""
        # v1: [10, 20, 30], v2: [11, 21, 30]
        facts_v1 = [
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 10},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK28", "date": "2026-07-13", "quantity": 20},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK29", "date": "2026-07-20", "quantity": 30},
        ]
        facts_v2 = [
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 11},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK28", "date": "2026-07-13", "quantity": 21},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK29", "date": "2026-07-20", "quantity": 30},
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-15", fact_rows=facts_v1)
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=facts_v2)
        _make_week_dt_range(db, make_week_dt,
                            ("2026-07-06", "2026-07-13", "2026-07-20"),
                            (27, 28, 29))

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-15", "2026-06-29"],
            years=[2026],
            query_diff=True,
        )
        result = pivot_query.query_pivot(db, req)
        assert result.period_columns == ["2026-07-06", "2026-07-13"]
        assert result.total_rows == 2
        for r in result.row_groups:
            expected = {
                "2026-07-06": 10 if r.version_date == "2026-06-15" else 11,
                "2026-07-13": 20 if r.version_date == "2026-06-15" else 21,
            }
            assert r.quantities == expected
            # quantity 是原值，不是 delta（不会是 ±1 / ±x 等差值）
            for v in r.quantities.values():
                assert v in (10, 11, 20, 21)

    # ---- #5 ----

    def test_query_diff_multi_business_groups_union_columns(
        self, db, make_dsp_upload, make_week_dt
    ):
        """业务组 A 仅有 p1 差异、业务组 B 仅有 p2 差异 → period_columns 是并集。

        每个 row_group.quantities 仅保留自己业务组的差异日期；不含对方业务组的差异日期。
        """
        # 业务组 A：v1/v2 在 07-06 相同 (100/100)，07-13 不同 (80/90)，07-20 相同 (50/50)
        facts_a_v1 = [
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 100},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK28", "date": "2026-07-13", "quantity": 80},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK29", "date": "2026-07-20", "quantity": 50},
        ]
        facts_a_v2 = [
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 100},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK28", "date": "2026-07-13", "quantity": 90},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK29", "date": "2026-07-20", "quantity": 50},
        ]
        # 业务组 B：v1/v2 在 07-06 相同 (30/30)，07-13 相同 (50/50)，07-20 不同 (20/35)
        facts_b_v1 = [
            {"country": "马来西亚", "category": "光模块",
             "config_code": "Y456", "config_name": "100G-LR4",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 30},
            {"country": "马来西亚", "category": "光模块",
             "config_code": "Y456", "config_name": "100G-LR4",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK28", "date": "2026-07-13", "quantity": 50},
            {"country": "马来西亚", "category": "光模块",
             "config_code": "Y456", "config_name": "100G-LR4",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK29", "date": "2026-07-20", "quantity": 20},
        ]
        facts_b_v2 = [
            {"country": "马来西亚", "category": "光模块",
             "config_code": "Y456", "config_name": "100G-LR4",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 30},
            {"country": "马来西亚", "category": "光模块",
             "config_code": "Y456", "config_name": "100G-LR4",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK28", "date": "2026-07-13", "quantity": 50},
            {"country": "马来西亚", "category": "光模块",
             "config_code": "Y456", "config_name": "100G-LR4",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK29", "date": "2026-07-20", "quantity": 35},
        ]
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-15",
                        fact_rows=facts_a_v1 + facts_b_v1)
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29",
                        fact_rows=facts_a_v2 + facts_b_v2)
        _make_week_dt_range(db, make_week_dt,
                            ("2026-07-06", "2026-07-13", "2026-07-20"),
                            (27, 28, 29))

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-15", "2026-06-29"],
            years=[2026],
            query_diff=True,
        )
        result = pivot_query.query_pivot(db, req)
        # 业务组 A 保 07-13；业务组 B 保 07-20；并集 → period_columns
        assert result.period_columns == ["2026-07-13", "2026-07-20"]
        assert result.total_rows == 4  # 2 业务组 × 2 version_date
        # 业务组 A 的 2 行 quantities 仅含 07-13
        a_rows = [r for r in result.row_groups
                  if r.country == "爱尔兰" and r.config_code == "X123"]
        assert len(a_rows) == 2
        for r in a_rows:
            assert r.quantities == {
                "2026-07-13": 80 if r.version_date == "2026-06-15" else 90,
            }
        # 业务组 B 的 2 行 quantities 仅含 07-20
        b_rows = [r for r in result.row_groups
                  if r.country == "马来西亚" and r.config_code == "Y456"]
        assert len(b_rows) == 2
        for r in b_rows:
            assert r.quantities == {
                "2026-07-20": 20 if r.version_date == "2026-06-15" else 35,
            }

    # ---- #6 ----

    def test_query_diff_does_not_affect_demand_plus_supply(
        self, db, make_dsp_upload, make_week_dt
    ):
        """`pivot_type='demand_plus_supply'` + `query_diff=True` → 4 行不变，全保留。"""
        facts = [
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Demand", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 100},
            {"country": "爱尔兰", "category": "交换机整机",
             "config_code": "X123", "config_name": "32Q-TOR-T3",
             "data_type": "Supply", "ttl": 4,
             "ym": "2026-07", "week": "WK27", "date": "2026-07-06", "quantity": 130},
        ]
        # demand_plus_supply 仅支持单 version_date，本身就 < 1 守卫命中
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=facts)
        make_week_dt(db, "2026-07-06", year_id=2026, month_id=7,
                     week_id=27, is_week_start=True)

        from app.schemas import PivotQueryRequest

        req = PivotQueryRequest(
            pivot_type="demand_plus_supply",
            vendor="Arista", item="X", sub_item="Y",
            version_dates=["2026-06-29"],
            years=[2026],
            query_diff=True,
        )
        result = pivot_query.query_pivot(db, req)
        # _apply_diff_filter 不接通 → 4 行 + 全保留
        assert result.total_rows == 4
        types = [r.data_type for r in result.row_groups]
        assert types == ["Demand", "Supply", "TTL_GAP", "Rolling_TTLGAP"]
        assert result.period_columns == ["2026-07-06"]
        expected_map = {
            "Demand": 100,
            "Supply": 130,
            "TTL_GAP": 30,        # 130 - 100
            "Rolling_TTLGAP": 30,  # 累积 = 当前 30
        }
        for r in result.row_groups:
            assert r.quantities == {"2026-07-06": expected_map[r.data_type]}

    # ---- API 端到端 bonus ----

    @pytest.mark.asyncio
    async def test_query_diff_api_default_drops_equal_dates(
        self, client, db, make_dsp_upload, make_week_dt
    ):
        """API 端到端：默认 query_diff=true + 2 版本 + 某日期两版相同 → period_columns 收缩。"""
        facts_v1, facts_v2 = _make_two_versions_facts(50, 50)  # 全等 → 全剪除
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-15", fact_rows=facts_v1)
        make_dsp_upload(db, vendor="Arista", item="X", sub_item="Y",
                        version_date="2026-06-29", fact_rows=facts_v2)
        _make_week_dt_range(db, make_week_dt,
                            ("2026-07-06", "2026-07-13", "2026-07-20"),
                            (27, 28, 29))

        payload = {
            "pivot_type": "demand",
            "vendor": "Arista", "item": "X", "sub_item": "Y",
            "version_dates": ["2026-06-15", "2026-06-29"],
            "years": [2026],
            # query_diff 不传 → 默认 True
        }
        resp = await client.post("/api/pivot-query", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        # 3 个日期全等 → period_columns 为空数组
        assert body["period_columns"] == []
        # 2 个 row_group（每 version_date 一条），quantities 全空
        assert body["total_rows"] == 2
        for rg in body["row_groups"]:
            assert rg["quantities"] == {}