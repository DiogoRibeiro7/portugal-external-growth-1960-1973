"""Application settings and repository paths."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PEG_", extra="ignore")

    root: Path = Field(default=Path("."))
    start_year: int = Field(default=1960, ge=1900, le=2100)
    end_year: int = Field(default=1973, ge=1900, le=2100)
    http_timeout_seconds: int = Field(default=60, ge=1, le=600)
    comtrade_subscription_key: str | None = None

    def resolved_root(self) -> Path:
        """Return an absolute repository root path."""

        return self.root.expanduser().resolve()

    def validate_year_range(self) -> None:
        """Raise when the configured year range is reversed."""

        if self.start_year > self.end_year:
            raise ValueError("start_year must not be greater than end_year")
