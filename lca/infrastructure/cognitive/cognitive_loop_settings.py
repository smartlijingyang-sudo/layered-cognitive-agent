"""Cognitive loop feature flags.

设置只保留仍会改变认知循环语义的开关；事实写入没有双写或兼容旁路。
环境变量前缀为 ``LCA_LOOP_``。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Setting(str, Enum):
    """Canonical settings ids (the LCA_LOOP_* env vars)."""

    PersistFullPrompt = "persist_full_prompt"
    EnvelopeEnforce = "envelope_enforce"
    InboxFollowupUngate = "inbox_followup_ungate"


_SENTINEL = "LCA_LOOP_"


class CognitiveLoopSettings(BaseSettings):
    """仍处于显式治理下的认知循环配置。"""

    model_config = SettingsConfigDict(env_prefix=_SENTINEL, case_sensitive=False)

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


PersistFullPrompt = Setting.PersistFullPrompt
EnvelopeEnforce = Setting.EnvelopeEnforce
InboxFollowupUngate = Setting.InboxFollowupUngate
