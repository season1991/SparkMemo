"""conftest 配置。

测试数据库 URL 选择优先级：
1. OS env ``DATABASE_URL``（最高，pytest 启动时 export 即可覆盖）
2. ``backend/.env`` 文件存在 → 由 pydantic-settings 自动加载（推荐用 MySQL）
3. 都没有 → fallback 到 SQLite 临时文件 ``./.pytest_sparkmemo.db``（仅 dev 环境兜底）
"""

import os
from pathlib import Path

# 关闭 APScheduler 调度器，避免测试期间触发 00:00 任务或干扰单测
os.environ.setdefault("SCHEDULER_DISABLED", "1")

# 探测 .env；若存在就让 pydantic-settings 自然加载（不会 setdefault 拦截）
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if not os.environ.get("DATABASE_URL") and not ENV_FILE.exists():
    # 兜底：没有 .env 且未指定 env 时走 SQLite（便于首次运行）
    os.environ.setdefault(
        "DATABASE_URL",
        "sqlite:///" + os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", ".pytest_sparkmemo.db")
        ),
    )

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import create_engine, event, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import database as _database  # noqa: E402
from app import models  # noqa: E402
from app import deps  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

# 同进程建表（SQLite 行为）
if not os.path.exists(settings.DATABASE_URL.replace("sqlite:///", "", 1)):
    pass

engine = create_engine(settings.DATABASE_URL, future=True)

# SQLite 上需要显式开启外键约束；连接级别 PRAGMA
@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _):
    if engine.dialect.name == "sqlite":
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


_models_Base = models.Base if hasattr(models, "Base") else _database.Base
_models_Base.metadata.create_all(engine)


# 幂等 ALTER：v0.4 新增 send_time / active 列；测试 SQLite 已存在 DB 也能升级
def _ensure_email_config_columns_for_tests(engine) -> None:
    table = "email_config"
    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            cols = {row[1] for row in rows}
            if "send_time" not in cols:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN send_time VARCHAR(5) NOT NULL DEFAULT '08:00'"
                )
            if "active" not in cols:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN active BOOLEAN NOT NULL DEFAULT 0"
                )
        else:
            for col, ddl in (
                ("send_time", "VARCHAR(5) NOT NULL DEFAULT '08:00'"),
                ("active", "TINYINT(1) NOT NULL DEFAULT 0"),
            ):
                exists = conn.exec_driver_sql(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
                    (table, col),
                ).first()
                if not exists:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


_ensure_email_config_columns_for_tests(engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


# 把 app.database.SessionLocal 重定向到本次测试的 SessionLocal，使 service 层也走同一个连接
_database.SessionLocal = SessionLocal


@pytest.fixture
def db():
    """每个用例前清空表（依赖顺序），返回新的 Session。"""
    session = SessionLocal()
    # SQLite 与 MySQL 关闭外键的语法不同；Dialect 分支处理
    if engine.dialect.name == "sqlite":
        # 顺序按子表优先；week_dt 由测试 fixture 动态创建，可能存在也可能不存在
        for table_name in (
            "dsp_upload_rows",
            "dsp_uploads",
            "cross_table_fill_rows",
            "cross_table_fill_configs",
            "cross_table_fill_jobs",
            "tasks",
            "projects",
            "task_types",
            "companies",
            "email_config",
        ):
            session.execute(text(f"DELETE FROM {table_name}"))
        # week_dt 可能不存在（仅 pivot_query 测试会 CREATE），忽略错误
        try:
            session.execute(text("DELETE FROM week_dt"))
        except Exception:
            session.rollback()
    else:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table_name in (
            "dsp_upload_rows",
            "dsp_uploads",
            "cross_table_fill_rows",
            "cross_table_fill_configs",
            "cross_table_fill_jobs",
            "tasks",
            "projects",
            "task_types",
            "companies",
            "email_config",
            "week_dt",
        ):
            session.execute(text(f"DELETE FROM {table_name}"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def today(monkeypatch):
    """把 scheduler.date.today 固定为 2026-08-10（spec 测试约定）。"""
    import app.services.scheduler as scheduler

    class FixedDate(__import__("datetime").date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 10)

    monkeypatch.setattr(scheduler, "date", FixedDate, raising=False)
    return "2026-08-10"


@pytest.fixture
async def client(db):
    """注入 FastAPI 测试 client（基于 ASGITransport）。"""
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


# ---------- 工厂 fixture ----------

@pytest.fixture
def make_company():
    def factory(db, name="ACME 集团", notes=None):
        company = models.Company(name=name, notes=notes)
        db.add(company)
        db.commit()
        db.refresh(company)
        return company

    return factory


@pytest.fixture
def make_project():
    def factory(db, company_id, name="Q3 备货", notes=None):
        project = models.Project(company_id=company_id, name=name, notes=notes)
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    return factory


@pytest.fixture
def make_task_type():
    def factory(db, name="会议"):
        task_type = models.TaskType(name=name)
        db.add(task_type)
        db.commit()
        db.refresh(task_type)
        return task_type

    return factory


@pytest.fixture
def make_task():
    """创建任务：remind_start_at 默认 ``due_at - 1 day``，与旧 conftest 行为一致。"""
    from datetime import date, timedelta

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


@pytest.fixture
def make_email_config():
    """创建 email_config 单行（v0.4 含 send_time / active）。"""
    def factory(
        db,
        smtp_host="smtp.qq.com",
        smtp_port=465,
        smtp_user="user@qq.com",
        smtp_password="secret123",
        use_tls=True,
        sender_email="user@qq.com",
        sender_name="SparkMemo",
        recipient_email="user@qq.com",
        recipient_name=None,
        send_time="08:00",
        active=False,
    ):
        existing = db.get(models.EmailConfig, 1)
        if existing is not None:
            db.delete(existing)
            db.commit()
        row = models.EmailConfig(
            id=1,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            use_tls=use_tls,
            sender_email=sender_email,
            sender_name=sender_name,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            send_time=send_time,
            active=active,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    return factory


@pytest.fixture
def make_dsp_upload():
    """创建 dsp_uploads + 可选事实行；用于 list / get / rows / delete 的端点测试。"""
    from datetime import date

    def factory(
        db,
        *,
        vendor="Arista",
        item="网络设备DSP横版",
        sub_item="机箱",
        version_date="2026-07-15",
        source_filename="Arista-网络设备DSP横版-机箱-061626.xlsx",
        row_count=0,
        created_at=None,
        fact_rows=None,
    ):
        if created_at is None:
            created_at = date.today().isoformat()
        upload = models.DspUpload(
            vendor=vendor,
            item=item,
            sub_item=sub_item,
            version_date=version_date,
            source_filename=source_filename,
            row_count=row_count,
            created_at=created_at,
        )
        db.add(upload)
        db.commit()
        db.refresh(upload)
        if fact_rows:
            db.add_all([models.DspUploadRow(upload_id=upload.id, **fr) for fr in fact_rows])
            db.commit()
            if row_count == 0:
                upload.row_count = len(fact_rows)
                db.commit()
                db.refresh(upload)
        return upload

    return factory
