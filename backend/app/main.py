# SparkMemo API 入口
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import companies, dashboard, email_config, projects, task_types, tasks
from app.services.scheduler import apscheduler_instance


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期：启动时启动调度器，关闭时停止调度器。"""
    apscheduler_instance.start()
    try:
        yield
    finally:
        if apscheduler_instance.running:
            apscheduler_instance.shutdown(wait=False)


app = FastAPI(title="SparkMemo", version="0.1.0", lifespan=lifespan)


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