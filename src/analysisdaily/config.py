"""集中配置：pydantic-settings + .env 加载。所有外部凭据均为可选。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 数据库（可选） ----
    database_url: str = ""

    # ---- 外部数据源密钥（可选） ----
    ground_news_api_key: str = ""
    allsides_api_key: str = ""
    wire_earth_api_key: str = ""

    # ---- LLM 事实引擎（可选） ----
    llm_provider: Literal["openai", "anthropic", "ollama", "none"] = "none"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: int = 60

    # ---- 分发（可选，填了对应配置才启用） ----
    smtp_host: str = ""
    smtp_port: str = ""
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    notion_token: str = ""
    notion_database_id: str = ""
    notion_page_id: str = ""

    # ---- Embedding 后端 ----
    embedding_backend: Literal["auto", "sentence_transformers", "tfidf", "hashing"] = "auto"
    embedding_model: str = "BAAI/bge-m3"

    # ---- 聚类 ----
    cluster_window_hours: int = 24
    cluster_min_samples: int = 2

    # ---- 数据目录 ----
    app_data_dir: Path = Path("./data")

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _llm_provider_default(cls, v):
        return "none" if v in (None, "") else v

    @field_validator("embedding_backend", mode="before")
    @classmethod
    def _embedding_backend_default(cls, v):
        return "auto" if v in (None, "") else v

    @field_validator("cluster_min_samples")
    @classmethod
    def _min_samples_ge2(cls, v: int) -> int:
        return max(2, v)

    def ensure_dirs(self) -> None:
        for sub in ("raw", "meta", "clusters", "reports", "e2e_sample"):
            (self.app_data_dir / sub).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s