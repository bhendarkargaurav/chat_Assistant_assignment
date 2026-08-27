from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Lenny Growth Assistant", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    database_url: str = Field(
        default="postgresql://lenny:lenny@localhost:5432/lenny_assistant",
        alias="DATABASE_URL",
    )

    llm_provider: Literal["ollama", "openai", "anthropic"] = Field(
        default="ollama",
        alias="LLM_PROVIDER",
    )

    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
    )
    ollama_model: str = Field(default="llama3.2", alias="OLLAMA_MODEL")
    ollama_embedding_model: str = Field(
        default="nomic-embed-text",
        alias="OLLAMA_EMBEDDING_MODEL",
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-3-5-haiku-20241022",
        alias="ANTHROPIC_MODEL",
    )

    embedding_dimension: int = Field(default=768, alias="EMBEDDING_DIMENSION")
    chunk_size: int = Field(default=800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=150, alias="CHUNK_OVERLAP")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    rag_essay_top_k: int = Field(default=8, alias="RAG_ESSAY_TOP_K")

    log_format: Literal["text", "json"] = Field(default="text", alias="LOG_FORMAT")

    llm_timeout_seconds: float = Field(default=180.0, alias="LLM_TIMEOUT_SECONDS")
    llm_max_attempts: int = Field(default=3, alias="LLM_MAX_ATTEMPTS")
    embedding_timeout_seconds: float = Field(
        default=60.0, alias="EMBEDDING_TIMEOUT_SECONDS"
    )
    embedding_max_attempts: int = Field(default=3, alias="EMBEDDING_MAX_ATTEMPTS")
    retry_base_delay_seconds: float = Field(
        default=0.5, alias="RETRY_BASE_DELAY_SECONDS"
    )

    router_mode: Literal["hybrid", "rules", "llm"] = Field(
        default="hybrid", alias="ROUTER_MODE"
    )
    router_confidence_threshold: float = Field(
        default=0.45, alias="ROUTER_CONFIDENCE_THRESHOLD"
    )

    conversation_history_limit: int = Field(
        default=10, alias="CONVERSATION_HISTORY_LIMIT"
    )

    essay_target_words: int = Field(default=1250, alias="ESSAY_TARGET_WORDS")
    essay_word_tolerance: float = Field(default=0.12, alias="ESSAY_WORD_TOLERANCE")
    essay_max_expansions: int = Field(default=1, alias="ESSAY_MAX_EXPANSIONS")

    artifact_max_bytes: int = Field(default=1_000_000, alias="ARTIFACT_MAX_BYTES")


@lru_cache
def get_settings() -> Settings:
    return Settings()
