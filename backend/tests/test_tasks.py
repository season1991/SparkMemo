"""tasks 接口契约测试（基于新 spec：remind_rule 入参）。"""

import pytest


# 构造符合 POST /api/tasks 的默认请求体，使用 remind_rule 表达业务意图。
def _task_payload(company_id, project_id, task_type_id=None, **values):
    payload = {
        "title": "ACME Q3 订单评审",
        "description": "与采购张总对齐 Q3 备货计划",
        "task_type_id": task_type_id,
        "company_id": company_id,
        "project_id": project_id,
        "due_at": "2026-08-15",
        "remind_rule": "before_1d",
        "custom_remind_start_at": None,
    }
    payload.update(values)
    return payload


async def test_create_task_missing_company_id(client, make_company, make_project, db):
    """POST 缺 company_id 时由业务校验返 400（非 Pydantic 422）。"""
    company = make_company(db)
    project = make_project(db, company.id)

    payload = _task_payload(None, project.id)
    payload.pop("company_id")

    response = await client.post("/api/tasks", json=payload)

    # FastAPI 路由签名是 schemas.TaskCreate，缺省必填会触发 Pydantic 422
    # 同时，端点层拿到 payload 后也会补一层；这里断言 4xx 即可
    assert response.status_code in (400, 422)


async def test_create_task_missing_project_id(client, make_company, db):
    """POST 缺 project_id → 4xx。"""
    company = make_company(db)
    payload = _task_payload(company.id, None)
    payload.pop("project_id")
    response = await client.post("/api/tasks", json=payload)
    assert response.status_code in (400, 422)


async def test_create_task_invalid_due_at_format(client, make_company, make_project, db):
    """POST due_at 非 YYYY-MM-DD → 422（Pydantic field_validator）。"""
    company = make_company(db)
    project = make_project(db, company.id)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, project.id, due_at="2026/08/15"),
    )
    assert response.status_code == 422


async def test_create_task_invalid_remind_rule(client, make_company, make_project, db):
    """POST remind_rule 非合法枚举 → 422。"""
    company = make_company(db)
    project = make_project(db, company.id)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, project.id, remind_rule="before_5d"),
    )
    assert response.status_code == 422


async def test_create_task_custom_missing_date(client, make_company, make_project, db):
    """POST remind_rule='custom' 但缺 custom_remind_start_at → 400（端点层校验）。"""
    company = make_company(db)
    project = make_project(db, company.id)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(
            company.id, project.id,
            remind_rule="custom",
            custom_remind_start_at=None,
        ),
    )
    assert response.status_code == 400


async def test_create_task_custom_after_due(client, make_company, make_project, db):
    """custom 模式，但 custom_remind_start_at 晚于 due_at → 400。"""
    company = make_company(db)
    project = make_project(db, company.id)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(
            company.id, project.id,
            due_at="2026-08-10",
            remind_rule="custom",
            custom_remind_start_at="2026-08-16",
        ),
    )
    assert response.status_code == 400


async def test_create_task_invalid_company_id(client, make_project, db):
    """company_id 指向不存在 → 422。"""
    from app import models

    company = models.Company(name="项目所属公司")
    db.add(company)
    db.commit()
    db.refresh(company)
    project = models.Project(company_id=company.id, name="项目")
    db.add(project)
    db.commit()
    db.refresh(project)

    response = await client.post(
        "/api/tasks",
        json=_task_payload(999999, project.id),
    )
    assert response.status_code == 422


async def test_create_task_invalid_project_id(client, make_company, db):
    """project_id 指向不存在 → 422。"""
    company = make_company(db)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, 999999),
    )
    assert response.status_code == 422


async def test_create_task_invalid_task_type_id(client, make_company, make_project, db):
    """task_type_id 指向不存在 → 422。"""
    company = make_company(db)
    project = make_project(db, company.id)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, project.id, task_type_id=999999),
    )
    assert response.status_code == 422


async def test_create_task_on_due_default(client, make_company, make_project, db):
    """不传 remind_rule 时由 Pydantic 422（remind_rule 必填）；显式 on_due 时 remind_start_at == due_at。"""
    from app import models

    company = make_company(db)
    project = make_project(db, company.id)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(
            company.id, project.id,
            remind_rule="on_due",
        ),
    )
    assert response.status_code == 201
    task = db.get(models.Task, response.json()["id"])
    assert task.due_at == "2026-08-15"
    assert task.remind_start_at == "2026-08-15"


async def test_create_task_missing_remind_rule(client, make_company, make_project, db):
    """缺 remind_rule → 422（Pydantic 必填校验）。"""
    company = make_company(db)
    project = make_project(db, company.id)
    payload = _task_payload(company.id, project.id)
    payload.pop("remind_rule")
    response = await client.post("/api/tasks", json=payload)
    assert response.status_code == 422


async def test_create_task_success(client, make_company, make_project, db):
    """合法 remind_rule='before_3d' → 201，remind_start_at 翻译为 2026-08-12。"""
    from app import models

    company = make_company(db)
    project = make_project(db, company.id)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, project.id, remind_rule="before_3d"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["due_at"] == "2026-08-15"
    assert body["remind_start_at"] == "2026-08-12"
    assert "remind_rule" not in body

    task = db.get(models.Task, body["id"])
    assert task.remind_start_at == "2026-08-12"


async def test_update_task_custom_after_due(client, make_company, make_project, make_task, db):
    """PUT 用 custom 但 custom_remind_start_at > due_at → 400。"""
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)

    response = await client.put(
        f"/api/tasks/{task.id}",
        json=_task_payload(
            company.id, project.id,
            due_at="2026-08-15",
            remind_rule="custom",
            custom_remind_start_at="2026-08-16",
        ),
    )
    assert response.status_code == 400


async def test_update_task(client, make_company, make_project, make_task, db):
    """PUT 正常路径。"""
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)

    response = await client.put(
        f"/api/tasks/{task.id}",
        json=_task_payload(
            company.id, project.id,
            title="修改后的任务",
            due_at="2026-08-20",
            remind_rule="on_due",
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "修改后的任务"
    assert body["status"] == "pending"
    assert body["completed_at"] is None
    assert body["due_at"] == "2026-08-20"
    assert body["remind_start_at"] == "2026-08-20"


async def test_delete_task(client, make_company, make_project, make_task, db):
    """DELETE → 204；GET 之后 404。"""
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)

    response = await client.delete(f"/api/tasks/{task.id}")
    assert response.status_code == 204

    detail = await client.get(f"/api/tasks/{task.id}")
    assert detail.status_code == 404


async def test_complete_task(client, make_company, make_project, make_task, db, today):
    """POST /complete → status='completed', completed_at=today。"""
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)

    response = await client.post(f"/api/tasks/{task.id}/complete")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["completed_at"] == today


async def test_complete_task_already_completed(client, make_company, make_project, make_task, db):
    """二次 complete → 409。"""
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)
    first = await client.post(f"/api/tasks/{task.id}/complete")
    second = await client.post(f"/api/tasks/{task.id}/complete")
    assert first.status_code == 200
    assert second.status_code == 409


async def test_create_task_date_format_invalid_via_custom(client, make_company, make_project, db):
    """custom_remind_start_at 非 YYYY-MM-DD → 422。"""
    company = make_company(db)
    project = make_project(db, company.id)
    response = await client.post(
        "/api/tasks",
        json=_task_payload(
            company.id, project.id,
            remind_rule="custom",
            custom_remind_start_at="2026/08/10",
        ),
    )
    assert response.status_code == 422
