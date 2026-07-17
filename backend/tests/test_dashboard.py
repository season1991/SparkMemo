"""今日概述接口测试集 - 严格基线 + 三档分桶 + 全公司列出。

完全遵循 spec/dashboard.md §Test Plan 的 17 条用例。
运行：pytest backend/tests/test_dashboard.py -v
"""
import re

import pytest


# ========== 1. 响应结构 ==========

async def test_response_shape(client, db, make_company):
    """1：响应字段 `today` / `summary` / `companies[]` 完整；嵌套结构稳定。"""
    make_company(db, name="A")

    resp = await client.get("/api/dashboard/today")

    assert resp.status_code == 200
    body = resp.json()
    assert body["today"] == "2026-08-10"
    assert set(body["summary"].keys()) == {"urgent", "due_soon", "early", "total"}
    assert isinstance(body["companies"], list)
    assert len(body["companies"]) == 1
    c = body["companies"][0]
    assert set(c.keys()) == {
        "company_id", "company_name", "urgent", "due_soon", "early", "total",
    }


async def test_summary_equals_sum_of_companies(
    client, db, make_company, make_project, make_task,
):
    """2：summary 各字段等于 companies[] 同名字段之和，防止双源真理。"""
    a = make_company(db, name="A")
    b = make_company(db, name="B")
    pa = make_project(db, a.id, name="pA")
    pb = make_project(db, b.id, name="pB")
    make_task(db, a.id, pa.id, due_at="2026-08-10", remind_start_at="2026-08-05")
    make_task(db, a.id, pa.id, due_at="2026-08-11", remind_start_at="2026-08-05")
    make_task(db, b.id, pb.id, due_at="2026-08-12", remind_start_at="2026-08-05")

    resp = await client.get("/api/dashboard/today")
    body = resp.json()
    assert body["summary"]["urgent"] == sum(c["urgent"] for c in body["companies"])
    assert body["summary"]["due_soon"] == sum(c["due_soon"] for c in body["companies"])
    assert body["summary"]["early"] == sum(c["early"] for c in body["companies"])
    assert body["summary"]["total"] == sum(c["total"] for c in body["companies"])


async def test_company_total_equals_bucket_sum(
    client, db, make_company, make_project, make_task,
):
    """3：每家公司 total == urgent + due_soon + early。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    make_task(db, a.id, pa.id, due_at="2026-08-10", remind_start_at="2026-08-05")
    make_task(db, a.id, pa.id, due_at="2026-08-12", remind_start_at="2026-08-05")
    make_task(db, a.id, pa.id, due_at="2026-08-15", remind_start_at="2026-08-05")

    resp = await client.get("/api/dashboard/today")
    body = resp.json()
    for c in body["companies"]:
        assert c["total"] == c["urgent"] + c["due_soon"] + c["early"], c


# ========== 2. 三档分桶 ==========

async def test_urgent_only_due_today(
    client, db, make_company, make_project, make_task,
):
    """4：紧急档只命中 `due_at == today`；边界 today-1 / today+1 不进 urgent。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    # 已逾期 (due < today) - 严格基线排除
    make_task(db, a.id, pa.id, due_at="2026-08-09", remind_start_at="2026-08-05")
    # 今日到期 (due == today)
    make_task(db, a.id, pa.id, due_at="2026-08-10", remind_start_at="2026-08-05")
    # 临期 (due = today+1)
    make_task(db, a.id, pa.id, due_at="2026-08-11", remind_start_at="2026-08-05")

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["urgent"] == 1
    assert a_row["due_soon"] == 1
    assert a_row["early"] == 0
    assert a_row["total"] == 2


async def test_urgent_excludes_overdue_pending(
    client, db, make_company, make_project, make_task,
):
    """5：`due_at < today` 的 pending 不入任何档（严格基线 = remind_start<=today<=due）。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    make_task(db, a.id, pa.id, due_at="2026-08-09", remind_start_at="2026-08-05")

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["urgent"] == 0
    assert a_row["due_soon"] == 0
    assert a_row["early"] == 0
    assert a_row["total"] == 0


async def test_due_soon_within_3d(
    client, db, make_company, make_project, make_task,
):
    """6：due_soon = `today < due_at <= today+3` 闭开区间正确。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    for offset in (1, 2, 3):
        day = f"2026-08-{10 + offset:02d}"
        make_task(db, a.id, pa.id, due_at=day, remind_start_at="2026-08-05")

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["due_soon"] == 3
    assert a_row["urgent"] == 0
    assert a_row["early"] == 0


async def test_due_soon_excludes_today(
    client, db, make_company, make_project, make_task,
):
    """7：今日到期优先归 urgent；三档边界不重叠。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    make_task(db, a.id, pa.id, due_at="2026-08-10", remind_start_at="2026-08-05")

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["urgent"] == 1
    assert a_row["due_soon"] == 0


async def test_early_due_after_3d(
    client, db, make_company, make_project, make_task,
):
    """8：early = `due_at > today+3`。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    make_task(db, a.id, pa.id, due_at="2026-08-14", remind_start_at="2026-08-05")
    make_task(db, a.id, pa.id, due_at="2026-08-20", remind_start_at="2026-08-05")

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["early"] == 2
    assert a_row["urgent"] == 0
    assert a_row["due_soon"] == 0


async def test_buckets_mutually_exclusive(
    client, db, make_company, make_project, make_task,
):
    """9：同一任务三档仅落一档（端到端互斥校验）。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    make_task(db, a.id, pa.id, due_at="2026-08-10", remind_start_at="2026-08-05")  # urgent
    make_task(db, a.id, pa.id, due_at="2026-08-11", remind_start_at="2026-08-05")  # due_soon
    make_task(db, a.id, pa.id, due_at="2026-08-15", remind_start_at="2026-08-05")  # early

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["urgent"] == 1
    assert a_row["due_soon"] == 1
    assert a_row["early"] == 1
    assert a_row["total"] == 3


# ========== 3. 状态过滤 ==========

async def test_excludes_completed(
    client, db, make_company, make_project, make_task,
):
    """10：completed 任务不计入任何档。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    make_task(
        db, a.id, pa.id,
        due_at="2026-08-10", remind_start_at="2026-08-05",
        status="completed", completed_at="2026-08-09",
    )

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["urgent"] == 0
    assert a_row["total"] == 0


async def test_excludes_overdue_done(
    client, db, make_company, make_project, make_task,
):
    """11：overdue_done 任务不计入任何档。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    make_task(
        db, a.id, pa.id,
        due_at="2026-08-10", remind_start_at="2026-08-05",
        status="overdue_done", completed_at="2026-08-15",
    )

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["total"] == 0


async def test_excludes_remind_in_future(
    client, db, make_company, make_project, make_task,
):
    """12：remind_start > today 的任务不计入（严格基线上界）。"""
    a = make_company(db, name="A")
    pa = make_project(db, a.id)
    make_task(db, a.id, pa.id, due_at="2026-08-15", remind_start_at="2026-08-11")

    resp = await client.get("/api/dashboard/today")
    a_row = _row_of(resp.json(), a.id)
    assert a_row["total"] == 0


# ========== 4. 边界 / 排序 / SQL 守护 ==========

async def test_empty_company_included_with_zero_counts(client, db, make_company):
    """13：0 任务公司仍出现在 companies[]，四档计数全 0。"""
    a = make_company(db)

    resp = await client.get("/api/dashboard/today")
    body = resp.json()
    assert len(body["companies"]) == 1
    c = body["companies"][0]
    assert c["company_id"] == a.id
    assert c["urgent"] == 0
    assert c["due_soon"] == 0
    assert c["early"] == 0
    assert c["total"] == 0
    assert body["summary"]["total"] == 0


async def test_sort_total_desc_then_urgent_then_name(
    client, db, make_company, make_project, make_task,
):
    """14：排序 = `total DESC, urgent DESC, company_name ASC`；插入顺序打乱仍按规则排。"""
    # 故意按打乱顺序插入：Delta → ACME → Gamma → Beta
    delta = make_company(db, name="Delta")
    acme = make_company(db, name="ACME")
    gamma = make_company(db, name="Gamma")
    beta = make_company(db, name="Beta")
    p_acme = make_project(db, acme.id, name="pA")
    p_beta = make_project(db, beta.id, name="pB")
    p_gamma = make_project(db, gamma.id, name="pG")
    p_delta = make_project(db, delta.id, name="pD")

    # ACME: total=10, urgent=3 → 3 urgent + 3 due_soon + 4 early
    for _ in range(3):
        make_task(db, acme.id, p_acme.id, due_at="2026-08-10", remind_start_at="2026-08-05")
    for _ in range(3):
        make_task(db, acme.id, p_acme.id, due_at="2026-08-11", remind_start_at="2026-08-05")
    for _ in range(4):
        make_task(db, acme.id, p_acme.id, due_at="2026-08-15", remind_start_at="2026-08-05")

    # Beta: total=10, urgent=2 → 2 urgent + 5 due_soon + 3 early
    for _ in range(2):
        make_task(db, beta.id, p_beta.id, due_at="2026-08-10", remind_start_at="2026-08-05")
    for _ in range(5):
        make_task(db, beta.id, p_beta.id, due_at="2026-08-11", remind_start_at="2026-08-05")
    for _ in range(3):
        make_task(db, beta.id, p_beta.id, due_at="2026-08-15", remind_start_at="2026-08-05")

    # Gamma: total=5, urgent=0 → 5 early
    for _ in range(5):
        make_task(db, gamma.id, p_gamma.id, due_at="2026-08-15", remind_start_at="2026-08-05")

    # Delta: total=5, urgent=0 → 5 early
    for _ in range(5):
        make_task(db, delta.id, p_delta.id, due_at="2026-08-15", remind_start_at="2026-08-05")

    resp = await client.get("/api/dashboard/today")
    names = [c["company_name"] for c in resp.json()["companies"]]
    # Gamma(C) 与 Delta(D) 两者 total=5/urgent=0 时按 name ASC：Delta < Gamma
    assert names == ["ACME", "Beta", "Delta", "Gamma"]


async def test_sql_no_db_date_func(client, db, make_company, monkeypatch):
    """15：SQL 文本不含 CURDATE()/NOW()/CURRENT_DATE/GETDATE()；日期以命名参数传入。"""
    make_company(db, name="A")
    statements = []
    execute = db.execute

    def capture(statement, *args, **kwargs):
        statements.append(str(statement))
        return execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", capture)

    resp = await client.get("/api/dashboard/today")
    assert resp.status_code == 200

    sql = "\n".join(statements).upper()
    assert not re.search(r"CURDATE\(\)|NOW\(\)|CURRENT_DATE|GETDATE\(\)", sql), sql
    # 命名参数必须出现在 SQL 文本中
    assert ":TODAY" in sql, sql
    assert ":SOON_CUTOFF" in sql, sql


@pytest.mark.parametrize("keep_company", [True, False])
async def test_empty_db_returns_zero_summary_empty_companies(
    client, db, make_company, keep_company,
):
    """16：空库边界 —— summary 全 0；两种形态：保留 1 家公司 / 全空 companies。"""
    if keep_company:
        make_company(db, name="Empty")

    resp = await client.get("/api/dashboard/today")
    body = resp.json()
    assert body["summary"] == {"urgent": 0, "due_soon": 0, "early": 0, "total": 0}
    if keep_company:
        assert len(body["companies"]) == 1
        assert body["companies"][0]["total"] == 0
    else:
        assert body["companies"] == []


async def test_today_field_reflects_python_today(client):
    """17：响应 today 字段等于 conftest 注入的 python date（与 scheduler.get_today 同源）。"""
    resp = await client.get("/api/dashboard/today")
    assert resp.status_code == 200
    assert resp.json()["today"] == "2026-08-10"


# ========== 工具函数 ==========

def _row_of(body: dict, company_id: int) -> dict:
    """从响应 companies[] 中取出指定公司的行；用于单公司场景。"""
    for c in body["companies"]:
        if c["company_id"] == company_id:
            return c
    raise AssertionError(f"company_id={company_id} not found in response: {body}")
