# 从接口响应中提取列表数据，兼容直接返回数组和带 items 的分页响应。
def _items(response):
    body = response.json()
    if isinstance(body, dict):
        return body["items"]
    return body


# 验证 POST /api/companies 使用合法 name 和 notes 创建公司，返回 201 并回显自增 id。
async def test_create_company_success(client):
    response = await client.post(
        "/api/companies",
        json={"name": "ACME 集团", "notes": "主要客户 A"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "ACME 集团"
    assert body["notes"] == "主要客户 A"
    assert isinstance(body["id"], int)


# 验证 POST /api/companies 缺少必填字段 name 时由请求校验拒绝，返回 422。
async def test_create_company_missing_name(client):
    response = await client.post("/api/companies", json={"notes": "无名称"})

    assert response.status_code == 422


# 验证 companies.name 全表唯一：同名请求第一次返回 201，第二次触发唯一冲突返回 409。
async def test_create_company_duplicate_name(client):
    payload = {"name": "ACME 集团"}
    first = await client.post("/api/companies", json=payload)
    second = await client.post("/api/companies", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


# 验证 GET /api/companies?keyword=AC 按公司名称模糊匹配，只返回名称中包含 AC 的公司。
async def test_list_companies_keyword_fuzzy(client):
    await client.post("/api/companies", json={"name": "ACME 集团"})
    await client.post("/api/companies", json={"name": "Beta 有限公司"})

    response = await client.get("/api/companies", params={"keyword": "AC"})

    assert response.status_code == 200
    companies = _items(response)
    assert [company["name"] for company in companies] == ["ACME 集团"]


# 验证公司列表 page=2、size=10 的分页契约：25 条数据应返回第二页 10 条且 total 为 25。
async def test_list_companies_pagination(client):
    for index in range(25):
        response = await client.post(
            "/api/companies",
            json={"name": f"公司 {index:02d}"},
        )
        assert response.status_code == 201

    response = await client.get(
        "/api/companies",
        params={"page": 2, "size": 10},
    )

    assert response.status_code == 200
    companies = _items(response)
    assert len(companies) == 10
    assert response.json()["total"] == 25


# 验证 GET /api/companies/{id} 返回指定公司的详情，并保留 notes 备注字段。
async def test_get_company_detail(client, make_company, db):
    company = make_company(db, notes="客户备注")

    response = await client.get(f"/api/companies/{company.id}")

    assert response.status_code == 200
    assert response.json()["id"] == company.id
    assert response.json()["notes"] == "客户备注"


# 验证查询不存在的公司 id 按错误约定返回 404，而不是返回空对象或 500。
async def test_get_company_not_found(client):
    response = await client.get("/api/companies/999999")

    assert response.status_code == 404


# 验证 PUT /api/companies/{id} 可以同时修改公司名称和备注，并返回更新后的资源。
async def test_update_company(client, make_company, db):
    company = make_company(db)

    response = await client.put(
        f"/api/companies/{company.id}",
        json={"name": "新公司名称", "notes": "更新后的备注"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "新公司名称"
    assert body["notes"] == "更新后的备注"


# 验证删除未被项目或任务引用的公司返回 204，删除后再次查询应返回 404。
async def test_delete_company_success(client, make_company, db):
    company = make_company(db)

    response = await client.delete(f"/api/companies/{company.id}")

    assert response.status_code == 204
    detail = await client.get(f"/api/companies/{company.id}")
    assert detail.status_code == 404


# 验证公司被 projects.company_id 外键引用时采用软阻断策略，删除必须返回 409。
async def test_delete_company_referenced_by_project(
    client,
    make_company,
    make_project,
    db,
):
    company = make_company(db)
    make_project(db, company.id)

    response = await client.delete(f"/api/companies/{company.id}")

    assert response.status_code == 409


# 验证公司被 tasks.company_id 外键直接引用时同样禁止删除，并返回 409。
async def test_delete_company_referenced_by_task(
    client,
    make_company,
    make_project,
    make_task,
    db,
):
    company = make_company(db)
    project = make_project(db, company.id)
    make_task(db, company.id, project.id)

    response = await client.delete(f"/api/companies/{company.id}")

    assert response.status_code == 409
