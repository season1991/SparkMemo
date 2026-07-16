# 从接口响应中提取列表数据，兼容直接返回数组和带 items 的分页响应。
def _items(response):
    body = response.json()
    if isinstance(body, dict):
        return body["items"]
    return body


# 验证 GET /api/task-types 不启用分页，创建三个类型后应完整返回三条记录。
async def test_list_task_types_no_pagination(client):
    for name in ("会议", "电话", "跟进"):
        response = await client.post("/api/task-types", json={"name": name})
        assert response.status_code == 201

    response = await client.get("/api/task-types")

    assert response.status_code == 200
    assert len(_items(response)) == 3


# 验证 POST /api/task-types 使用合法 name 创建任务类型，返回 201 和自增 id。
async def test_create_task_type_success(client):
    response = await client.post("/api/task-types", json={"name": "会议"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "会议"
    assert isinstance(body["id"], int)


# 验证 task_types.name 全表唯一：重复创建同名类型时第二次返回 409。
async def test_create_task_type_duplicate_name(client):
    payload = {"name": "会议"}
    first = await client.post("/api/task-types", json=payload)
    second = await client.post("/api/task-types", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


# 验证 PUT /api/task-types/{id} 修改类型名称，并返回更新后的名称。
async def test_update_task_type(client, make_task_type, db):
    task_type = make_task_type(db)

    response = await client.put(
        f"/api/task-types/{task_type.id}",
        json={"name": "客户回访"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "客户回访"


# 验证 GET /api/task-types/{id} 返回指定类型的 id 和 name 详情。
async def test_get_task_type_detail(client, make_task_type, db):
    task_type = make_task_type(db)

    response = await client.get(f"/api/task-types/{task_type.id}")

    assert response.status_code == 200
    assert response.json()["id"] == task_type.id
    assert response.json()["name"] == task_type.name


# 验证查询不存在的任务类型 id 按统一错误约定返回 404。
async def test_get_task_type_not_found(client):
    response = await client.get("/api/task-types/999999")

    assert response.status_code == 404


# 验证删除未被任务引用的类型返回 204，随后查询该类型应返回 404。
async def test_delete_task_type_success(client, make_task_type, db):
    task_type = make_task_type(db)

    response = await client.delete(f"/api/task-types/{task_type.id}")

    assert response.status_code == 204
    detail = await client.get(f"/api/task-types/{task_type.id}")
    assert detail.status_code == 404


# 验证 task_type_id 外键被任务引用时采用软阻断策略，删除类型返回 409。
async def test_delete_task_type_referenced_by_task(
    client,
    make_company,
    make_project,
    make_task_type,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    task_type = make_task_type(db)
    make_task(db, company.id, project.id, task_type_id=task_type.id)

    response = await client.delete(f"/api/task-types/{task_type.id}")

    assert response.status_code == 409
