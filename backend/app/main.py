# SparkMemo API 入口
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import companies, projects, task_types, tasks
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
app.include_router(companies.router)
app.include_router(projects.router)
app.include_router(task_types.router)
app.include_router(tasks.router)