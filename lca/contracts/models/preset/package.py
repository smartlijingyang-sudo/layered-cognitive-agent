"""Domain models for Preset and Authored Plugins (DDD)."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PresetScope(StrEnum):
    """Scope defining isolation, visibility, and storage topology."""

    PRIVATE = "private"
    SHARED = "shared"
    PLATFORM = "platform"


class AuthoredPlugin(BaseModel):
    """A user- or agent-authored plugin artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    code: str
    path: str = ""
    capabilities: tuple[str, ...] = ()
    side_effects: str = "none"
    policy_class: str = "execute"
    implements: tuple[str, ...] = ("Plugin",)


class PresetPackage(BaseModel):
    """A complete bundled preset package containing metadata and authored plugins."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    preset_id: str
    scope: PresetScope = PresetScope.PRIVATE
    assistant_id: str | None = None
    description: str = ""
    plugins: tuple[AuthoredPlugin, ...] = ()
    bundle_manifest: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


__all__ = [
    "AuthoredPlugin",
    "PresetPackage",
    "PresetScope",
]
