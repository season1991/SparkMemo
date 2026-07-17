import re


# 从任务列表响应中提取数据，兼容分页对象和直接数组两种列表响应形态。
def _items(response):
    body = response.json()
    if isinstance(body, dict):
        return body["items"]
    return body


# 构造任务提醒相关接口的默认请求体，新 spec 用 remind_rule 入参。
def _task_payload(company_id, project_id, **values):
    payload = {
        "title": "提醒任务",
        "description": "提醒测试",
        "company_id": company_id,
        "project_id": project_id,
        "due_at": "2026-08-15",
        "remind_rule": "before_1d",
        "custom_remind_start_at": None,
    }
    payload.update(values)
    return payload


# 验证提醒计划闭区间 [2026-08-08, 2026-08-15] 每天生成一条记录，共 8 条并包含起止日。
def test_compute_reminders_unit_8_days():
    from app.services.reminders import compute_reminders

    reminders = compute_reminders("2026-08-08", "2026-08-15")

    assert len(reminders) == 8
    assert reminders[0] == {"remind_at": "2026-08-08"}
    assert reminders[-1] == {"remind_at": "2026-08-15"}


# 验证提醒计划跨两天时仅返回 08-14 和 08-15 两条，不提前或延后生成记录。
def test_compute_reminders_unit_2_days():
    from app.services.reminders import compute_reminders

    reminders = compute_reminders("2026-08-14", "2026-08-15")

    assert reminders == [
        {"remind_at": "2026-08-14"},
        {"remind_at": "2026-08-15"},
    ]


# 验证 remind_start_at 与 due_at 同日时仍按闭区间规则生成 1 条当天提醒。
def test_compute_reminders_unit_same_day():
    from app.services.reminders import compute_reminders

    reminders = compute_reminders("2026-08-15", "2026-08-15")

    assert reminders == [{"remind_at": "2026-08-15"}]


# 验证 GET /api/tasks/{id} 实时计算 reminders，并返回 08-08 至 08-15 的完整提醒数组。
async def test_get_task_includes_reminders(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(
        db,
        company.id,
        project.id,
        due_at="2026-08-15",
        remind_start_at="2026-08-08",
    )

    response = await client.get(f"/api/tasks/{task.id}")

    assert response.status_code == 200
    assert response.json()["reminders"] == [
        {"remind_at": f"2026-08-{day:02d}"} for day in range(8, 16)
    ]


# 验证修改 due_at + remind_rule 后无需重建提醒数据，下一次详情查询立即反映新计划。
async def test_update_task_reminders_reflect_new_plan(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(
        db,
        company.id,
        project.id,
        due_at="2026-08-15",
        remind_start_at="2026-08-08",
    )

    # PUT 改为 before_1d → 后端翻译为 remind_start_at=2026-08-14
    update = await client.put(
        f"/api/tasks/{task.id}",
        json=_task_payload(
            company.id,
            project.id,
            title=task.title,
            due_at="2026-08-15",
            remind_rule="before_1d",
            custom_remind_start_at=None,
        ),
    )
    detail = await client.get(f"/api/tasks/{task.id}")

    assert update.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["due_at"] == "2026-08-15"
    assert detail.json()["remind_start_at"] == "2026-08-14"
    assert detail.json()["reminders"] == [
        {"remind_at": "2026-08-14"},
        {"remind_at": "2026-08-15"},
    ]


# 验证 remind_today=true 在注入 today=2026-08-10 时只返回 pending 且处于提醒区间的任务。
async def test_remind_today_returns_in_window(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    in_window = make_task(
        db,
        company.id,
        project.id,
        title="窗口内",
        due_at="2026-08-15",
        remind_start_at="2026-08-08",
    )
    make_task(
        db,
        company.id,
        project.id,
        title="窗口外",
        due_at="2026-08-15",
        remind_start_at="2026-08-11",
    )

    response = await client.get(
        "/api/tasks",
        params={"remind_today": "true"},
    )

    assert response.status_code == 200
    tasks = _items(response)
    assert [task["id"] for task in tasks] == [in_window.id]


# 验证 remind_today=true 自动排除 status=completed 的任务，即使今天仍落在提醒日期区间内。
async def test_remind_today_excludes_completed(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    make_task(
        db,
        company.id,
        project.id,
        title="已完成",
        status="completed",
        completed_at="2026-08-09",
        due_at="2026-08-15",
        remind_start_at="2026-08-08",
    )

    response = await client.get("/api/tasks?remind_today=true")

    assert response.status_code == 200
    assert _items(response) == []


# 验证 remind_today=true 自动排除 status=overdue_done 的任务，避免已自动完成任务继续提醒。
async def test_remind_today_excludes_overdue_done(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    make_task(
        db,
        company.id,
        project.id,
        title="逾期完成",
        status="overdue_done",
        completed_at="2026-08-10",
        due_at="2026-08-15",
        remind_start_at="2026-08-08",
    )

    response = await client.get("/api/tasks?remind_today=true")

    assert response.status_code == 200
    assert _items(response) == []


# 验证 remind_start_at=2026-08-11 晚于 today=2026-08-10 时，尚未开始的 pending 任务不返回。
async def test_remind_today_excludes_not_started(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    make_task(
        db,
        company.id,
        project.id,
        title="尚未开始",
        due_at="2026-08-15",
        remind_start_at="2026-08-11",
    )

    response = await client.get("/api/tasks?remind_today=true")

    assert response.status_code == 200
    assert _items(response) == []


# 验证 due_at=2026-08-09 早于 today=2026-08-10 时，提醒窗口已结束的 pending 任务不返回。
async def test_remind_today_excludes_finished_window(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    make_task(
        db,
        company.id,
        project.id,
        title="已结束",
        due_at="2026-08-09",
        remind_start_at="2026-08-08",
    )

    response = await client.get("/api/tasks?remind_today=true")

    assert response.status_code == 200
    assert _items(response) == []


# 验证 remind_today 查询使用 Python 传入 today 参数，生成的 SQL 不依赖 CURDATE、NOW 等数据库日期函数。
async def test_remind_today_sql_no_db_date_func(
    client,
    make_company,
    make_project,
    make_task,
    db,
    monkeypatch,
):
    company = make_company(db)
    project = make_project(db, company.id)
    make_task(db, company.id, project.id)
    statements = []
    execute = db.execute

    def capture(statement, *args, **kwargs):
        statements.append(str(statement))
        return execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", capture)
    response = await client.get("/api/tasks?remind_today=true")

    assert response.status_code == 200
    sql = "\n".join(statements).upper()
    assert not re.search(r"CURDATE\(\)|NOW\(\)|CURRENT_DATE|GETDATE\(\)", sql)
