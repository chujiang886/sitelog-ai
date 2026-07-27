"""Environment-based application configuration."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 加载 BOIP 根目录 .env（含 LLM_A_* 真实 key 等），确保在任何 Agent 运行时读取
# os.environ 之前注入环境变量。本模块在 app 启动时即被导入，早于请求处理。
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / ".env")


class Settings(BaseSettings):
    """Validated BOIP backend settings loaded from environment variables."""

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    redis_url: str = Field(default="", validation_alias="REDIS_URL")
    qdrant_url: str = Field(default="", validation_alias="QDRANT_URL")
    minio_endpoint: str = Field(default="", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="", validation_alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="", validation_alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="", validation_alias="MINIO_BUCKET")
    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings snapshot."""

    return Settings()
