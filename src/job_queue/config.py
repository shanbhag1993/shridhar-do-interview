from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    host: str = "0.0.0.0"
    port: int = Field(default=8000, gt=0, lt=65536)
    log_level: str = "INFO"

    queue_capacity: int = Field(default=10_000, gt=0)
    num_workers: int = Field(default=16, gt=0)

    # ops/DEPLOYMENT_PLAN.md names this RETENTION_TTL, so both names are accepted.
    retention_ttl_seconds: float = Field(
        default=3600,
        gt=0,
        validation_alias=AliasChoices("RETENTION_TTL_SECONDS", "RETENTION_TTL"),
    )
    cleaner_interval_seconds: float = Field(default=60, gt=0)

    drain_timeout_seconds: float = Field(default=30, gt=0)

    retry_backoff_base_seconds: float = Field(default=0.5, gt=0)
    retry_backoff_max_seconds: float = Field(default=30, gt=0)

    # Advertised to clients on 429 responses.
    retry_after_seconds: int = Field(default=3, gt=0)
