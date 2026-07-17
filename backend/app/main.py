# SparkMemo API 入口
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import companies, dashboard, dsp_uploads, email_config, email_send, projects, task_types, tasks
from app.services.scheduler import apscheduler_instance, sync_email_dispatch_job


def _ensure_email_config_columns(engine) -> None:
    """幂等 ALTER：v0.4 新增 send_time / active；已有 MySQL 实例升级时补列。

    双方言分支：SQLite 用 PRAGMA table_info；MySQL 用 information_schema.columns。
    """
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
        else:  # MySQL / 其他
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：

    启动顺序：幂等 ALTER email_config 新列 → 按 DB 现状同步 email_daily_dispatch
    Job → 启动调度器。关闭时停止调度器。
    """
    from app.database import SessionLocal

    engine = _app.state._engine if hasattr(_app.state, "_engine") else None
    if engine is None:
        from app.database import engine as _engine

        engine = _engine

    _ensure_email_config_columns(engine)

    # 按 DB 现状同步调度器（升级用户 active=true → 立即 resume）
    db = SessionLocal()
    try:
        from app.crud.email_config import get_email_config

        cfg = get_email_config(db)
        sync_email_dispatch_job(cfg)
    finally:
        db.close()

    apscheduler_instance.start()
    try:
        yield
    finally:
        if apscheduler_instance.running:
            apscheduler_instance.shutdown(wait=False)


app = FastAPI(title="SparkMemo", version="0.4.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def _email_config_validation_handler(request: Request, exc: RequestValidationError):
    """邮箱配置路由下的字段校验失败 → 400（满足 spec 错误约定）。

    仅对 /api/email-config 路径生效，其他路由保持默认 422 行为。
    """
    if not request.url.path.startswith("/api/email-config"):
        # 其他路由：复刻 FastAPI 默认行为（422），用 jsonable_encoder 处理 ValueError 等不可序列化对象
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(exc.errors())},
        )
    errors = exc.errors()
    message = errors[0]["msg"] if errors else "invalid request"
    return JSONResponse(status_code=400, content={"detail": message})


app.include_router(companies.router)
app.include_router(projects.router)
app.include_router(task_types.router)
app.include_router(tasks.router)
app.include_router(dashboard.router)
app.include_router(email_config.router)
app.include_router(email_send.router)
app.include_router(dsp_uploads.router)