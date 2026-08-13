"""Shared secret for the stack-local host sidecar. Not user login."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class PresenceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LCA_HOST_", extra="ignore")

    token: str = "lca-local-host"  # noqa: S105 — stack-local shared secret, not a user password
    subject: str = "local-dev-user"
