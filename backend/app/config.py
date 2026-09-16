"""Central configuration.

Every knob an operator can turn lives here and is sourced from the environment.
Nothing in `app/` reads `os.environ` directly, so switching model providers,
retrieval weights, or safety limits never requires an application code change.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ChatProvider = Literal["ollama", "anthropic", "openai", "echo"]
EmbeddingProvider = Literal["ollama", "openai", "hash"]
AgentRuntime = Literal["native", "claude_sdk"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- service ---------------------------------------------------------
    app_name: str = "The Lenny Growth Assistant"
    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ---- database --------------------------------------------------------
    database_url: str = "postgresql+asyncpg://lenny:lenny@postgres:5432/lenny"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_connect_timeout_s: int = 5

    # ---- chat model ------------------------------------------------------
    chat_provider: ChatProvider = "ollama"
    chat_fallback_provider: ChatProvider | None = None

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_chat_model: str = "llama3.1:8b"
    ollama_embedding_model: str = "nomic-embed-text"

    anthropic_api_key: str | None = None
    anthropic_chat_model: str = "claude-sonnet-4-5"

    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    max_output_tokens: int = 4096
    temperature: float = 0.2
    request_timeout_s: int = 180

    # ---- embeddings ------------------------------------------------------
    embedding_provider: EmbeddingProvider = "ollama"
    embedding_dim: int = 768

    # ---- agent -----------------------------------------------------------
    agent_runtime: AgentRuntime = "native"
    max_tool_iterations: int = 4

    # ---- retrieval -------------------------------------------------------
    retrieval_top_k: int = 8
    retrieval_candidate_k: int = 30
    rrf_k: int = 60
    min_grounding_score: float = 0.018
    chunk_target_tokens: int = 700
    chunk_overlap_tokens: int = 100
    history_turns_in_context: int = 8

    # ---- artifacts / safety ---------------------------------------------
    artifact_max_bytes: int = 400_000
    allow_artifact_scripts: bool = True

    @field_validator("cors_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """psycopg-style URL, used by the bootstrap migration runner."""
        return self.database_url.replace("+asyncpg", "").replace(
            "postgresql://", "postgresql://"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
