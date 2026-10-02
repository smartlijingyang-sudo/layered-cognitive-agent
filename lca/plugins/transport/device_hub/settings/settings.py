"""Device-gateway settings — service token, JWT secret, SQLite path."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DeviceHubSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LCA_DEVICE_", extra="ignore")

    service_token: str = "lca-local-host"  # noqa: S105 — empty default; real value from LCA_DEVICE_ env
    jwt_secret: str = ""
    db_path: str = "traces/devices.db"
    subject: str = "local-dev-user"
    api_keys: tuple[str, ...] = ()
