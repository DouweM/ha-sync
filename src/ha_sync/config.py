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

    @property
    def templates_path(self) -> Path:
        return Path("templates")

    @property
    def groups_path(self) -> Path:
        return Path("groups")

    def ensure_dirs(self) -> None:
        """Create all required directories."""
        self.dashboards_path.mkdir(parents=True, exist_ok=True)
        self.automations_path.mkdir(parents=True, exist_ok=True)
        self.scripts_path.mkdir(parents=True, exist_ok=True)
        self.scenes_path.mkdir(parents=True, exist_ok=True)
        for helper_type in [
            "input_boolean",
            "input_number",
            "input_select",
            "input_text",
            "input_datetime",
        ]:
            (self.helpers_path / helper_type).mkdir(parents=True, exist_ok=True)
        self.templates_path.mkdir(parents=True, exist_ok=True)
        self.groups_path.mkdir(parents=True, exist_ok=True)

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
