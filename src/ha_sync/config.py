"""Configuration management for ha-sync."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SyncConfig(BaseSettings):
    """Configuration loaded from .env file."""

    ha_url: str = Field(default="", alias="HA_URL")
    ha_token: str = Field(default="", alias="HA_TOKEN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def url(self) -> str:
        """Get HA URL."""
        return self.ha_url

    @property
    def token(self) -> str:
        """Get HA token."""
        return self.ha_token

    @property
    def dashboards_path(self) -> Path:
        return Path("dashboards")

    @property
    def automations_path(self) -> Path:
        return Path("automations")

    @property
    def scripts_path(self) -> Path:
        return Path("scripts")

    @property
    def scenes_path(self) -> Path:
        return Path("scenes")

    @property
    def helpers_path(self) -> Path:
        return Path("helpers")

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.dashboards_path.mkdir(parents=True, exist_ok=True)
        self.automations_path.mkdir(parents=True, exist_ok=True)
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        self.scenes_path.mkdir(parents=True, exist_ok=True)
        # WebSocket-based helpers
        for helper_type in [
            "input_boolean",
            "input_number",
            "input_select",
            "input_text",
            "input_datetime",
            "input_button",
            "timer",
            "schedule",
            "counter",
        ]:
            (self.helpers_path / helper_type).mkdir(parents=True, exist_ok=True)
        # Template and group helpers (subdirs created on demand)
        (self.helpers_path / "template").mkdir(parents=True, exist_ok=True)
        (self.helpers_path / "group").mkdir(parents=True, exist_ok=True)

    @classmethod
    def is_configured(cls) -> bool:
        """Check if .env exists with required config."""
        config = cls()
        return bool(config.ha_url and config.ha_token)


# Alias for backward compatibility
Settings = SyncConfig


def get_config() -> SyncConfig:
    """Get the sync configuration."""
    return SyncConfig()
