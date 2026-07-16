# SparkMemo FastAPI 依赖项
from app.database import SessionLocal


def get_db():
    """FastAPI 依赖：每次请求创建独立数据库会话，请求结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()