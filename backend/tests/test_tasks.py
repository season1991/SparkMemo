from app import models


# 构造符合 POST /api/tasks 示例契约的默认请求体，测试可覆盖指定字段而保留其他必填字段。
def _task_payload(company_id, project_id, task_type_id=None, **values):
    payload = {
        "title": "ACME Q3 订单评审",
        "description": "与采购张总对齐 Q3 备货计划",
        "task_type_id": task_type_id,
        "company_id": company_id,
        "project_id": project_id,
        "due_at": "2026-08-15",
        "remind_start_at": "2026-08-08",
    }
    payload.update(values)
    return payload


# 验证 POST /api/tasks 缺少必填 company_id 时返回 400，而不是把缺省字段当作无效外键处理。
async def test_create_task_missing_company_id(client, make_company, make_project, db):
    company = make_company(db)
    project = make_project(db, company.id)

    payload = _task_payload(None, project.id)
    payload.pop("company_id")
    response = await client.post(
        "/api/tasks",
        json=payload,
    )

    assert response.status_code == 400


# 验证 POST /api/tasks 缺少必填 project_id 时返回 400，符合任务创建字段约定。
async def test_create_task_missing_project_id(client, make_company, db):
    company = make_company(db)

    payload = _task_payload(company.id, None)
    payload.pop("project_id")
    response = await client.post(
        "/api/tasks",
        json=payload,
    )

    assert response.status_code == 400


# 验证 remind_start_at 晚于 due_at 时拒绝创建，返回日期关系错误 400。
async def test_create_task_remind_start_after_due(
    client,
    make_company,
    make_project,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)

    response = await client.post(
        "/api/tasks",
        json=_task_payload(
            company.id,
            project.id,
            remind_start_at="2026-08-16",
        ),
    )

    assert response.status_code == 400


# 验证 due_at 不符合 YYYY-MM-DD 格式时返回 400，不允许写入非 10 字符日期。
async def test_create_task_invalid_due_at_format(
    client,
    make_company,
    make_project,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)

    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, project.id, due_at="2026/08/15"),
    )

    assert response.status_code == 400


# 验证 remind_start_at 不符合 YYYY-MM-DD 格式时返回 400。
async def test_create_task_invalid_remind_start_format(
    client,
    make_company,
    make_project,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)

    response = await client.post(
        "/api/tasks",
        json=_task_payload(
            company.id,
            project.id,
            remind_start_at="2026/08/08",
        ),
    )

    assert response.status_code == 400


# 验证 company_id 指向不存在公司时返回外键无效错误 422。
async def test_create_task_invalid_company_id(client, make_project, db):
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


# 验证 project_id 指向不存在项目时返回外键无效错误 422。
async def test_create_task_invalid_project_id(client, make_company, db):
    company = make_company(db)

    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, 999999),
    )

    assert response.status_code == 422


# 验证可空 task_type_id 一旦传入不存在的类型 id，仍须按外键校验返回 422。
async def test_create_task_invalid_task_type_id(
    client,
    make_company,
    make_project,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)

    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, project.id, task_type_id=999999),
    )

    assert response.status_code == 422


# 验证创建任务后 due_at 和 remind_start_at 均按 spec 以 10 字符 YYYY-MM-DD 字符串入库。
async def test_create_task_due_at_stored_as_10_char(
    client,
    make_company,
    make_project,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)

    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, project.id),
    )

    assert response.status_code == 201
    task = db.get(models.Task, response.json()["id"])
    assert len(task.due_at) == 10
    assert len(task.remind_start_at) == 10


# 验证 POST /api/tasks 合法创建返回 201，且新任务状态默认为 pending。
async def test_create_task_success(client, make_company, make_project, db):
    company = make_company(db)
    project = make_project(db, company.id)

    response = await client.post(
        "/api/tasks",
        json=_task_payload(company.id, project.id),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"


# 验证请求省略 remind_start_at 时，后端按 due_at 减 1 天默认生成 2026-08-14。
async def test_create_task_default_remind_start_at(
    client,
    make_company,
    make_project,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)

    payload = _task_payload(company.id, project.id)
    payload.pop("remind_start_at")
    response = await client.post(
        "/api/tasks",
        json=payload,
    )

    assert response.status_code == 201
    assert response.json()["remind_start_at"] == "2026-08-14"


# 验证 PUT /api/tasks/{id} 修改任务字段后只更新请求内容，status 仍为 pending 且 completed_at 不被隐式写入。
async def test_update_task(client, make_company, make_project, make_task, db):
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)

    response = await client.put(
        f"/api/tasks/{task.id}",
        json=_task_payload(
            company.id,
            project.id,
            title="修改后的任务",
            due_at="2026-08-20",
            remind_start_at="2026-08-18",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "修改后的任务"
    assert body["status"] == "pending"
    assert body["completed_at"] is None


# 验证更新任务时同样执行 remind_start_at <= due_at 校验，非法日期关系返回 400。
async def test_update_task_invalid_dates(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)

    response = await client.put(
        f"/api/tasks/{task.id}",
        json=_task_payload(
            company.id,
            project.id,
            remind_start_at="2026-08-21",
            due_at="2026-08-20",
        ),
    )

    assert response.status_code == 400


# 验证 DELETE /api/tasks/{id} 返回 204，删除后任务详情接口返回 404 且不残留可查询记录。
async def test_delete_task(client, make_company, make_project, make_task, db):
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)

    response = await client.delete(f"/api/tasks/{task.id}")

    assert response.status_code == 204
    detail = await client.get(f"/api/tasks/{task.id}")
    assert detail.status_code == 404


# 验证 POST /api/tasks/{id}/complete 只允许 pending 转 completed，并写入注入的当天日期。
async def test_complete_task(
    client,
    make_company,
    make_project,
    make_task,
    db,
    today,
):
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)

    response = await client.post(f"/api/tasks/{task.id}/complete")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["completed_at"] == today


# 验证完成接口禁止 completed 任务再次完成，防止状态机发生非法重复跃迁并返回 409。
async def test_complete_task_already_completed(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    task = make_task(db, company.id, project.id)
    first = await client.post(f"/api/tasks/{task.id}/complete")
    second = await client.post(f"/api/tasks/{task.id}/complete")

    assert first.status_code == 200
    assert second.status_code == 409
