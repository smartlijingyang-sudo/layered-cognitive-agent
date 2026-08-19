"""Cognitive loop feature flags (PR2 / D15 / §25).

All flags live behind a single pydantic-settings object.  Defaults are
conservative: every new primitive dual-writes (per spec §25) and the
runtime keeps the legacy path green until the new path is fully
exercised.

Env prefix: ``LCA_LOOP_``.  Imports are typed via the ``Setting`` enum
so adding a flag is a single declaration.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Setting(str, Enum):
    """Canonical settings ids (the LCA_LOOP_* env vars)."""

    ContextManifestDualWriteEnabled = "context_manifest_dual_write"
    PersistFullPrompt = "persist_full_prompt"
    EnvelopeEnforce = "envelope_enforce"
    InboxFollowupUngate = "inbox_followup_ungate"


_SENTINEL = "LCA_LOOP_"


class CognitiveLoopSettings(BaseSettings):
    """Feature flags for the v3 cognitive loop rollout.

    Defaults: every new primitive dual-writes so the runtime stays green
    during the PR-by-PR landing.
    """

    model_config = SettingsConfigDict(env_prefix=_SENTINEL, case_sensitive=False)

    context_manifest_dual_write: bool = Field(
        default=True,
        description="Emit ContextManifested alongside the legacy path (PR2).",
    )
    persist_full_prompt: bool = Field(
        default=False,
        description="Persist full prompt_ref alongside digest (PR2 / D19).",
    )
    envelope_enforce: bool = Field(
        default=False,
        description="Enforce ExecutionEnvelope capability grant (PR6).",
    )
    inbox_followup_ungate: bool = Field(
        default=False,
        description="Ungate the inbox→followup routing (PR8 / D24).",
    )


_cached: CognitiveLoopSettings | None = None


def get_cognitive_loop_settings() -> CognitiveLoopSettings:
    """Return the cached settings (built once per process)."""
    global _cached
    if _cached is None:
        _cached = CognitiveLoopSettings()
    return _cached


def reset_cognitive_loop_settings(**overrides: Any) -> CognitiveLoopSettings:
    """Reset the cached settings with explicit overrides (test-only)."""
    global _cached
    _cached = CognitiveLoopSettings(**overrides)
    return _cached


ContextManifestDualWriteEnabled = Setting.ContextManifestDualWriteEnabled
PersistFullPrompt = Setting.PersistFullPrompt
EnvelopeEnforce = Setting.EnvelopeEnforce
InboxFollowupUngate = Setting.InboxFollowupUngate
