# -*- coding: utf-8 -*-
# @Time    : 2024/7/17 15:34
# @Author  : yangyuexiong
# @Email   : yang6333yyx@126.com
# @File    : config.py
# @Software: PyCharm

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV = "development"
ENV_FILE_ENV_VAR = "ENV_FILE"


def normalize_env(env: Optional[str]) -> str:
    value = (env or "").strip().lower()
    mapping = {
        "dev": "development",
        "development": "development",
        "test": "test",
        "testing": "test",
        "prod": "production",
        "production": "production",
        "stage": "staging",
        "staging": "staging",
    }
    return mapping.get(value, value or DEFAULT_ENV)


ENV_FILE_MAP = {
    "development": ".env.development",
    "test": ".env.test",
    "production": ".env.production",
    "staging": ".env.staging",
}


def resolve_env_files(env_name: str) -> List[Path]:
    if env_name not in ENV_FILE_MAP:
        raise ValueError(f"Unsupported ENV: {env_name}")

    paths: List[Path] = []

    explicit = os.getenv(ENV_FILE_ENV_VAR)
    if explicit:
        explicit_path = Path(explicit)
        if not explicit_path.is_absolute():
            explicit_path = BASE_DIR / explicit_path
        if explicit_path.exists():
            paths.append(explicit_path)
        else:
            raise FileNotFoundError(f"{ENV_FILE_ENV_VAR} 指定的文件不存在: {explicit_path}")

    base_env = BASE_DIR / ".env"
    if base_env.exists():
        paths.append(base_env)

    env_specific = BASE_DIR / ENV_FILE_MAP[env_name]
    if env_specific.exists():
        paths.append(env_specific)

    if paths:
        return paths

    raise FileNotFoundError(
        f"未找到配置文件，请创建 {ENV_FILE_MAP.get(env_name)} 或设置 {ENV_FILE_ENV_VAR}"
    )


"""
extra = 'allow' ✅
允许额外的字段（不在模型定义中的字段）

extra = 'ignore' ⚠️
忽略额外的字段

extra = 'forbid' ❌
禁止额外的字段
"""

BASE_SETTINGS_CONFIG = SettingsConfigDict(
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore",
)


class BaseConfig(BaseSettings):
    """配置基类"""

    model_config = BASE_SETTINGS_CONFIG

    # 基础配置
    APP_NAME: str = "yangyuexiong"
    ENV: str
    DB_BACKEND: str = "mysql"
    SECRET_KEY: str
    DEBUG: bool
    RUN_HOST: str
    RUN_PORT: int

    # MySQL配置
    MYSQL_HOSTNAME: str
    MYSQL_USERNAME: str
    MYSQL_PASSWORD: str
    MYSQL_PORT: int
    MYSQL_DATABASE: str

    # POSTGRESQL配置
    POSTGRESQL_HOSTNAME: str
    POSTGRESQL_USERNAME: str
    POSTGRESQL_PASSWORD: str
    POSTGRESQL_PORT: int
    POSTGRESQL_DATABASE: str

    # Redis配置
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PWD: str
    REDIS_DB: int
    DECODE_RESPONSES: bool
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_QUEUE: str = "exile_ai_tasks"

    # LLM配置
    LLM_TIMEOUT_SECONDS: int = 90
    LLM_DEV_PROVIDER: str = "deepseek"
    LLM_DEV_MODEL: str = "deepseek-chat"
    LLM_PROD_PROVIDER: str = "openai"
    LLM_PROD_MODEL: str = "gpt-4o-mini"
    LLM_DEFAULT_TEMPERATURE: float = 0.2
    LLM_MAX_HISTORY_MESSAGES: int = 40
    LLM_MAX_TOOL_STEPS: int = 4
    LLM_RATE_LIMIT_ENABLE: bool = True
    LLM_RATE_LIMIT_REQUESTS_PER_MINUTE: int = 20
    LLM_RATE_LIMIT_REQUESTS_PER_DAY: int = 500
    LLM_TOKEN_QUOTA_PER_DAY: int = 200000
    LLM_MEMORY_ENABLE: bool = True
    LLM_MEMORY_SUMMARY_TRIGGER_MESSAGES: int = 24
    LLM_MEMORY_KEEP_RECENT_MESSAGES: int = 12
    LLM_MEMORY_SUMMARY_MAX_CHARS: int = 2000
    LLM_AUTO_FALLBACK_ENABLE: bool = True
    LLM_FALLBACK_PROVIDERS: str = "deepseek,openai,gemini"

    LLM_ORCHESTRATOR: str = "legacy"
    LLM_AGENT_MAX_STEPS: int = 8
    LLM_AGENT_APPROVAL_MODE: str = "manual"
    LLM_AGENT_CHECKPOINT_BACKEND: str = "db"

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    GEMINI_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    GEMINI_MODEL: str = "gemini-2.0-flash"

    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # 日志脱敏配置
    SENSITIVE_HEADERS: str = "authorization,cookie,set-cookie,x-api-key"

    @property
    def ENV_NAME(self) -> str:
        return normalize_env(self.ENV)

    @property
    def IS_DEV(self) -> bool:
        return self.ENV_NAME == "development"

    @property
    def IS_TEST(self) -> bool:
        return self.ENV_NAME == "test"

    @property
    def IS_PROD(self) -> bool:
        return self.ENV_NAME == "production"

    @property
    def IS_STAGING(self) -> bool:
        return self.ENV_NAME == "staging"

    @property
    def MASK_SENSITIVE_HEADERS(self) -> bool:
        # 生产与预发布默认脱敏；如需调整可在此修改策略
        return self.IS_PROD or self.IS_STAGING

    @property
    def default_llm_provider(self) -> str:
        if self.IS_PROD or self.IS_STAGING:
            return (self.LLM_PROD_PROVIDER or "openai").strip().lower()
        return (self.LLM_DEV_PROVIDER or "deepseek").strip().lower()

    @property
    def default_llm_model(self) -> str:
        if self.IS_PROD or self.IS_STAGING:
            return (self.LLM_PROD_MODEL or "gpt-4o-mini").strip()
        return (self.LLM_DEV_MODEL or "deepseek-chat").strip()

    @property
    def redis_url(self) -> str:
        auth = f":{self.REDIS_PWD}@" if self.REDIS_PWD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}?decode_responses={self.DECODE_RESPONSES}"

    @property
    def redis_transport_url(self) -> str:
        auth = f":{self.REDIS_PWD}@" if self.REDIS_PWD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.redis_transport_url

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.redis_transport_url

    @property
    def mysql_url(self) -> str:
        return "mysql://{}:{}@{}:{}/{}".format(
            self.MYSQL_USERNAME,
            self.MYSQL_PASSWORD,
            self.MYSQL_HOSTNAME,
            self.MYSQL_PORT,
            self.MYSQL_DATABASE
        )

    @property
    def mysql_async_url(self) -> str:
        return "mysql+asyncmy://{}:{}@{}:{}/{}".format(
            self.MYSQL_USERNAME,
            self.MYSQL_PASSWORD,
            self.MYSQL_HOSTNAME,
            self.MYSQL_PORT,
            self.MYSQL_DATABASE
        )

    @property
    def pg_url(self) -> str:
        return "postgres://{}:{}@{}:{}/{}".format(
            self.POSTGRESQL_USERNAME,
            self.POSTGRESQL_PASSWORD,
            self.POSTGRESQL_HOSTNAME,
            self.POSTGRESQL_PORT,
            self.POSTGRESQL_DATABASE
        )

    @property
    def pg_async_url(self) -> str:
        return "postgresql+asyncpg://{}:{}@{}:{}/{}".format(
            self.POSTGRESQL_USERNAME,
            self.POSTGRESQL_PASSWORD,
            self.POSTGRESQL_HOSTNAME,
            self.POSTGRESQL_PORT,
            self.POSTGRESQL_DATABASE
        )

    @property
    def sqlalchemy_database_url(self) -> str:
        backend = (self.DB_BACKEND or "mysql").lower()
        if backend == "mysql":
            return self.mysql_async_url
        if backend in {"postgres", "postgresql"}:
            return self.pg_async_url
        raise ValueError(f"Unsupported DB_BACKEND: {self.DB_BACKEND}")


@lru_cache
def get_config(env: Optional[str] = None) -> BaseConfig:
    """获取配置文件"""

    fast_api_env = normalize_env(env or os.getenv("FAST_API_ENV", DEFAULT_ENV))
    env_files = resolve_env_files(fast_api_env)
    logger.info(f"加载配置: env={fast_api_env}, files={[str(p) for p in env_files]}")
    conf = BaseConfig(_env_file=[str(p) for p in env_files])
    if conf.ENV_NAME != fast_api_env:
        logger.warning(f"ENV 不一致：FAST_API_ENV={fast_api_env}, 配置 ENV={conf.ENV_NAME}")
    return conf


if __name__ == '__main__':
    dev_config = get_config("development")
    print(dev_config.model_dump())
    print(dev_config.APP_NAME)
    print(dev_config.MYSQL_HOSTNAME)

    pro_config = get_config("production")
    print(pro_config.model_dump())
