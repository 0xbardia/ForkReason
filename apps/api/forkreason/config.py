"""Application configuration.

All environment-specific settings live here. Startup validation must fail
with a concise, actionable message rather than a stack trace deep inside a
dependency (spec FR-I-011).
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---------------------------------------------------
    app_env: str = Field(default="development", alias="APP_ENV")
    app_url: str = Field(default="http://localhost:3111", alias="APP_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- API -----------------------------------------------------------
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8421, alias="API_PORT")
    api_public_url: str = Field(default="http://localhost:8421", alias="API_PUBLIC_URL")
    cors_origins: str = Field(
        default="http://localhost:3111", alias="CORS_ORIGINS"
    )

    # --- Database ------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://forkreason:forkreason@127.0.0.1:5432/forkreason",
        alias="DATABASE_URL",
    )

    # --- GitHub --------------------------------------------------------
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    github_api_base_url: str = Field(
        default="https://api.github.com", alias="GITHUB_API_BASE_URL"
    )

    # --- Analysis limits (spec FR-A-004) --------------------------------
    analysis_max_repo_mb: int = Field(default=48, alias="ANALYSIS_MAX_REPO_MB")
    analysis_max_file_mb: int = Field(default=1, alias="ANALYSIS_MAX_FILE_MB")
    analysis_max_files: int = Field(default=4000, alias="ANALYSIS_MAX_FILES")
    analysis_max_commits: int = Field(default=600, alias="ANALYSIS_MAX_COMMITS")
    analysis_timeout_seconds: int = Field(
        default=600, alias="ANALYSIS_TIMEOUT_SECONDS"
    )
    analysis_max_evidence_items: int = Field(
        default=120, alias="ANALYSIS_MAX_EVIDENCE_ITEMS"
    )
    analysis_worker_concurrency: int = Field(
        default=2, alias="ANALYSIS_WORKER_CONCURRENCY"
    )

    # --- Forensic tuning ----------------------------------------------
    max_excerpt_chars: int = Field(default=600, alias="MAX_EXCERPT_CHARS")
    max_manifest_digest_chars: int = Field(default=12000, alias="MAX_MANIFEST_DIGEST_CHARS")
    upstream_candidate_limit: int = Field(
        default=12, alias="UPSTREAM_CANDIDATE_LIMIT"
    )

    # --- Storage -------------------------------------------------------
    snapshot_dir: str = Field(default="/var/lib/forkreason/snapshots", alias="SNAPSHOT_DIR")

    # --- GenLayer ------------------------------------------------------
    genlayer_network: str = Field(default="studionet", alias="GENLAYER_NETWORK")
    genlayer_rpc_url: str = Field(
        default="https://studio.genlayer.com/api", alias="GENLAYER_RPC_URL"
    )
    genlayer_contract_address: str | None = Field(
        default=None, alias="GENLAYER_CONTRACT_ADDRESS"
    )

    # --- Public (forwarded to NEXT_PUBLIC_* by the web app only) --------
    next_public_app_url: str = Field(
        default="http://localhost:3111", alias="NEXT_PUBLIC_APP_URL"
    )
    next_public_api_url: str = Field(
        default="http://localhost:8421", alias="NEXT_PUBLIC_API_URL"
    )
    next_public_genlayer_network: str = Field(
        default="studionet", alias="NEXT_PUBLIC_GENLAYER_NETWORK"
    )
    next_public_genlayer_rpc_url: str = Field(
        default="https://studio.genlayer.com/api", alias="NEXT_PUBLIC_GENLAYER_RPC_URL"
    )
    next_public_genlayer_contract_address: str | None = Field(
        default=None, alias="NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS"
    )
    next_public_walletconnect_project_id: str | None = Field(
        default=None, alias="NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID"
    )

    @field_validator("log_level")
    @classmethod
    def _upper_log(cls, v: str) -> str:
        return v.upper()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    def public_snapshot(self) -> dict[str, str | None]:
        """Values safe to expose to the browser. Never includes secrets."""
        return {
            "NEXT_PUBLIC_APP_URL": self.next_public_app_url,
            "NEXT_PUBLIC_API_URL": self.next_public_api_url,
            "NEXT_PUBLIC_GENLAYER_NETWORK": self.next_public_genlayer_network,
            "NEXT_PUBLIC_GENLAYER_RPC_URL": self.next_public_genlayer_rpc_url,
            "NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS": (
                self.next_public_genlayer_contract_address
            ),
            "NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID": (
                self.next_public_walletconnect_project_id
            ),
        }

    def validate_startup(self, *, require_db: bool = True) -> None:
        """Fail fast with an actionable message. Raises RuntimeError."""
        problems: list[str] = []
        if require_db and not self.database_url:
            problems.append(
                "DATABASE_URL is not set. Copy .env.example to .env and set it, "
                "e.g. postgresql+psycopg://user:pass@host:5432/forkreason"
            )
        if not self.database_url.startswith(("postgresql", "sqlite")):
            problems.append(
                "DATABASE_URL must be a postgresql:// URL "
                f"(got: {self.database_url.split(':', 1)[0]})"
            )
        if self.analysis_max_repo_mb < 1 or self.analysis_max_repo_mb > 512:
            problems.append("ANALYSIS_MAX_REPO_MB must be between 1 and 512")
        if self.analysis_worker_concurrency < 1 or self.analysis_worker_concurrency > 8:
            problems.append("ANALYSIS_WORKER_CONCURRENCY must be between 1 and 8")
        if self.max_excerpt_chars < 80 or self.max_excerpt_chars > 4000:
            problems.append("MAX_EXCERPT_CHARS must be between 80 and 4000")
        if self.is_production and not self.github_token:
            problems.append(
                "GITHUB_TOKEN is required in production to avoid GitHub rate limits. "
                "A token needs no write scopes for public read-only access."
            )
        if problems:
            raise RuntimeError(
                "ForkReason configuration is invalid:\n"
                + "\n".join(f"  - {p}" for p in problems)
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()