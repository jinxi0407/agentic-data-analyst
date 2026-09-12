"""Central environment-based configuration for Agentic Data Analyst."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Union


def _load_dotenv(path: Union[str, Path] = ".env") -> None:
    """Load simple KEY=VALUE pairs from .env without requiring extra packages."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


@dataclass(frozen=True)
class Settings:
    dashscope_api_key: str
    dashscope_base_url: str
    qwen_chat_model: str
    qwen_embedding_model: str
    qwen_embedding_dimension: int

    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    mysql_root_password: str

    max_retry: int
    max_steps: int
    sql_max_rows: int

    api_host: str
    api_port: int
    ui_port: int
    schema_top_k: int
    schema_similarity_threshold: float
    agent_timeout_seconds: int

    @property
    def mysql_url_safe(self) -> str:
        return (
            f"mysql://{self.mysql_user}:***@"
            f"{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
        )


def load_settings() -> Settings:
    _load_dotenv()

    return Settings(
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        dashscope_base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1"),
        qwen_chat_model=os.getenv("QWEN_CHAT_MODEL", ""),
        qwen_embedding_model=os.getenv("QWEN_EMBEDDING_MODEL", ""),
        qwen_embedding_dimension=_get_int("QWEN_EMBEDDING_DIMENSION", 1024),
        mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        mysql_port=_get_int("MYSQL_PORT", 3307),
        mysql_database=os.getenv("MYSQL_DATABASE", "agentic_data_analyst"),
        mysql_user=os.getenv("MYSQL_USER", "agentic_user"),
        mysql_password=os.getenv("MYSQL_PASSWORD", ""),
        mysql_root_password=os.getenv("MYSQL_ROOT_PASSWORD", ""),
        max_retry=_get_int("MAX_RETRY", 2),
        max_steps=_get_int("MAX_STEPS", 15),
        sql_max_rows=_get_int("SQL_MAX_ROWS", 200),
        api_host=os.getenv("API_HOST", "127.0.0.1"),
        api_port=_get_int("API_PORT", 8002),
        ui_port=_get_int("UI_PORT", 8502),
        schema_top_k=_get_int("SCHEMA_TOP_K", 12),
        schema_similarity_threshold=float(os.getenv("SCHEMA_SIMILARITY_THRESHOLD", "0.15")),
        agent_timeout_seconds=_get_int("AGENT_TIMEOUT_SECONDS", 60),
    )


settings = load_settings()
