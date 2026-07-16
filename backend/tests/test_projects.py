# 从接口响应中提取列表数据，兼容直接返回数组和带 items 的分页响应。
def _items(response):
    body = response.json()
    if isinstance(body, dict):
        return body["items"]
    return body


# 验证 POST /api/projects 携带有效 company_id 创建项目，返回 201、归属公司和备注。
async def test_create_project_success(client, make_company, db):
    company = make_company(db)

    response = await client.post(
        "/api/projects",
        json={"company_id": company.id, "name": "Q3 备货", "notes": "项目备注"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["company_id"] == company.id
    assert body["name"] == "Q3 备货"
    assert body["notes"] == "项目备注"


# 验证 POST /api/projects 缺少必填 company_id 时按错误约定返回 400。
async def test_create_project_missing_company_id(client):
    response = await client.post("/api/projects", json={"name": "无归属项目"})

    assert response.status_code == 400


# 验证 project.company_id 指向不存在公司时拒绝创建，并返回外键无效错误 422。
async def test_create_project_invalid_company_id(client):
    response = await client.post(
        "/api/projects",
        json={"company_id": 999999, "name": "无效归属项目"},
    )

    assert response.status_code == 422


# 验证联合唯一约束 (company_id, name)：同一公司下重复项目名返回 409。
async def test_create_project_duplicate_in_same_company(
    client,
    make_company,
    db,
):
    company = make_company(db)
    payload = {"company_id": company.id, "name": "Q3 备货"}
    first = await client.post("/api/projects", json=payload)
    second = await client.post("/api/projects", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


# 验证联合唯一约束只限制同公司：不同 company_id 可以分别创建同名项目且都返回 201。
async def test_create_project_same_name_different_company(
    client,
    make_company,
    db,
):
    first_company = make_company(db, name="第一家公司")
    second_company = make_company(db, name="第二家公司")
    payload = {"name": "同名项目"}

    first = await client.post(
        "/api/projects",
        json={**payload, "company_id": first_company.id},
    )
    second = await client.post(
        "/api/projects",
        json={**payload, "company_id": second_company.id},
    )

    assert first.status_code == 201
    assert second.status_code == 201


# 验证 GET /api/projects?company_id=... 只返回指定公司名下的项目，不混入其他公司数据。
async def test_list_projects_filter_by_company(
    client,
    make_company,
    make_project,
    db,
):
    first_company = make_company(db, name="第一家公司")
    second_company = make_company(db, name="第二家公司")
    first_project = make_project(db, first_company.id, name="第一项目")
    make_project(db, second_company.id, name="第二项目")

    response = await client.get(
        "/api/projects",
        params={"company_id": first_company.id},
    )

    assert response.status_code == 200
    projects = _items(response)
    assert [project["id"] for project in projects] == [first_project.id]


# 验证 GET /api/projects?keyword=备货 按项目名称进行模糊搜索，只返回匹配项目。
async def test_list_projects_keyword(client, make_company, make_project, db):
    company = make_company(db)
    make_project(db, company.id, name="Q3 备货")
    make_project(db, company.id, name="Q4 复盘")

    response = await client.get(
        "/api/projects",
        params={"keyword": "备货"},
    )

    assert response.status_code == 200
    projects = _items(response)
    assert [project["name"] for project in projects] == ["Q3 备货"]


# 验证 GET /api/projects/{id} 返回项目详情、所属公司 id 及 notes 字段。
async def test_get_project_detail(client, make_company, make_project, db):
    company = make_company(db)
    project = make_project(db, company.id, notes="项目备注")

    response = await client.get(f"/api/projects/{project.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == project.id
    assert body["company_id"] == company.id
    assert body["notes"] == "项目备注"


# 验证 PUT /api/projects/{id} 修改项目名称和备注后返回最新资源内容。
async def test_update_project(client, make_company, make_project, db):
    company = make_company(db)
    project = make_project(db, company.id)

    response = await client.put(
        f"/api/projects/{project.id}",
        json={
            "company_id": company.id,
            "name": "更新后的项目",
            "notes": "更新后的备注",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "更新后的项目"
    assert body["notes"] == "更新后的备注"


# 验证删除项目返回 204，且删除后 GET /api/projects/{id} 返回 404。
async def test_delete_project(client, make_company, make_project, db):
    company = make_company(db)
    project = make_project(db, company.id)

    response = await client.delete(f"/api/projects/{project.id}")

    assert response.status_code == 204
    detail = await client.get(f"/api/projects/{project.id}")
    assert detail.status_code == 404
