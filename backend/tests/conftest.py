from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app import database, models
from app import deps
from app.main import app


# 每个测试复用应用配置的开发数据库，并按外键依赖顺序清空四张业务表，保证用例互相隔离。
@pytest.fixture
def db():
    session_factory = getattr(database, "SessionLocal")
    session = session_factory()
    session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for table_name in ("tasks", "projects", "task_types", "companies"):
        session.execute(text(f"TRUNCATE TABLE {table_name}"))
    session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


# 将 scheduler.date.today 固定为 spec 测试计划要求的 2026-08-10，避免依赖运行机器日期。
@pytest.fixture(autouse=True)
def today(monkeypatch):
    import app.services.scheduler as scheduler

    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 10)

    monkeypatch.setattr(scheduler, "date", FixedDate, raising=False)
    return "2026-08-10"


# 为 FastAPI 注入当前测试会话，并通过 AsyncClient 访问 /api 下的异步接口。
@pytest.fixture
async def client(db):
    get_db = getattr(deps, "get_db")

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        try:
            async_client = AsyncClient(app=app, base_url="http://testserver")
        except TypeError:
            async_client = AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://testserver",
            )
        async with async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


# 创建公司测试数据，支持覆盖名称和备注以复用公司引用场景。
@pytest.fixture
def make_company():
    def factory(db, name="ACME 集团", notes=None):
        company = models.Company(name=name, notes=notes)
        db.add(company)
        db.commit()
        db.refresh(company)
        return company

    return factory


# 创建指定 company_id 的项目测试数据，用于项目筛选和公司删除阻断场景。
@pytest.fixture
def make_project():
    def factory(db, company_id, name="Q3 备货", notes=None):
        project = models.Project(
            company_id=company_id,
            name=name,
            notes=notes,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    return factory


# 创建任务类型测试数据，用于类型 CRUD 及任务外键引用场景。
@pytest.fixture
def make_task_type():
    def factory(db, name="会议"):
        task_type = models.TaskType(name=name)
        db.add(task_type)
        db.commit()
        db.refresh(task_type)
        return task_type

    return factory


# 创建任务测试数据，覆盖日期、状态、完成日期和三类外键，便于验证任务及 Job 规则。
@pytest.fixture
def make_task():
    def factory(
        db,
        company_id,
        project_id,
        task_type_id=None,
        title="任务",
        description=None,
        due_at="2026-08-15",
        remind_start_at=None,
        status="pending",
        completed_at=None,
    ):
        if remind_start_at is None:
            remind_start_at = (
                date.fromisoformat(due_at) - timedelta(days=1)
            ).isoformat()
        task = models.Task(
            title=title,
            description=description,
            task_type_id=task_type_id,
            company_id=company_id,
            project_id=project_id,
            due_at=due_at,
            remind_start_at=remind_start_at,
            status=status,
            completed_at=completed_at,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    return factory
