"""验证 lookup + query 完整链路。"""
import sys
sys.path.insert(0, '.')

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.database import engine
from app import models


def setup_db():
    """创建测试数据 + week_dt 表。"""
    with engine.begin() as conn:
        # 1. 创建 week_dt 表（外部表，conftest 不建）
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS week_dt (
                dt VARCHAR(10) PRIMARY KEY,
                year_id SMALLINT NOT NULL,
                month_id TINYINT NOT NULL,
                week_id TINYINT NOT NULL,
                is_week_start TINYINT NOT NULL DEFAULT 0
            )
        """))
        # 2. 清空业务表
        for t in ("dsp_upload_rows", "dsp_uploads"):
            conn.execute(text(f"DELETE FROM {t}"))
        conn.execute(text("DELETE FROM week_dt"))
    with engine.begin() as conn:
        # 3. 插入 week_dt 测试数据（2025-01 的周一）
        week_dt = [
            ("2024-12-30", 2025, 12, 1, 1),
            ("2025-01-06", 2025, 1, 2, 1),
            ("2025-01-13", 2025, 1, 3, 1),
            ("2025-01-20", 2025, 1, 4, 1),
            ("2025-01-27", 2025, 1, 5, 1),
        ]
        for dt, y, m, w, s in week_dt:
            conn.execute(text(
                "INSERT INTO week_dt (dt, year_id, month_id, week_id, is_week_start) VALUES (:dt, :y, :m, :w, :s)"
            ), {"dt": dt, "y": y, "m": m, "w": w, "s": s})
    with engine.begin() as conn:
        # 4. 插入一个 dsp_uploads + dsp_upload_rows
        result = conn.execute(text("""
            INSERT INTO dsp_uploads (vendor, item, sub_item, version_date, source_filename, row_count, created_at)
            VALUES ('Arista', 'X', 'Y', '2026-06-29', 'test.xlsx', 2, '2026-07-18')
        """))
        upload_id = result.lastrowid
        for i, dt in enumerate(["2025-01-06", "2025-01-13"]):
            conn.execute(text("""
                INSERT INTO dsp_upload_rows
                (upload_id, country, category, config_code, config_name, data_type, ttl, ym, week, date, quantity)
                VALUES (:uid, '爱尔兰', '交换机整机', 'X123', '32Q-TOR-T3', 'Demand', 4, '2025-01', :wk, :dt, 100)
            """), {"uid": upload_id, "wk": f"WK{i+2}", "dt": dt})


def main():
    setup_db()
    print("Test data inserted.\n")

    with TestClient(app) as client:
        # 1. lookup countries
        r = client.get("/api/pivot-query/lookups/countries",
                        params={"vendor": "Arista", "item": "X", "sub_item": "Y",
                                 "version_dates": "2026-06-29"})
        print(f"[GET countries] {r.status_code}: {r.text[:200]}")

        # 2. lookup categories
        r = client.get("/api/pivot-query/lookups/categories",
                        params={"vendor": "Arista", "item": "X", "sub_item": "Y",
                                 "version_dates": "2026-06-29",
                                 "countries": "爱尔兰"})
        print(f"[GET categories] {r.status_code}: {r.text[:200]}")

        # 3. lookup weeks-of-month
        r = client.get("/api/pivot-query/lookups/weeks-of-month",
                        params={"year": 2025, "month": 1})
        print(f"[GET weeks-of-month] {r.status_code}: {r.text[:200]}")

        # 4. POST query
        r = client.post("/api/pivot-query", json={
            "pivot_type": "demand",
            "vendor": "Arista",
            "item": "X",
            "sub_item": "Y",
            "version_dates": ["2026-06-29"],
            "years": [2025],
            "months": [1],
        })
        print(f"[POST query] {r.status_code}: {r.text[:300]}")


if __name__ == "__main__":
    main()
