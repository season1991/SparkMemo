# SparkMemo 配置
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://root:root@localhost:3306/sparkmemo?charset=utf8mb4"
    SCAN_INTERVAL_SECONDS: int = 30
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()