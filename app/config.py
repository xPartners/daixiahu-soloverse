"""全局配置：基于 pydantic-settings，支持 .env 与环境变量。"""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 应用
    APP_NAME: str = "ybA2A"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/yba2a"

    # Elasticsearch
    ES_URL: str = "http://localhost:9200"
    ES_INDEX_POLICY: str = "yba2a_policy"
    ES_INDEX_RULE: str = "yba2a_rule"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "yba2a-files"
    MINIO_SECURE: bool = False

    # 大模型基座
    LLM_PROVIDER: Literal["openai", "qwen", "glm", "ollama"] = "openai"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 2048

    # 规则引擎
    DEFAULT_RULE_REGION: str = "110000"  # 北京行政区划代码


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
