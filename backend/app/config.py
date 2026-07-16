# SparkMemo 配置
class Settings:
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/sparkmemo?charset=utf8mb4"
    SCAN_INTERVAL_SECONDS: int = 30
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000


settings = Settings()
