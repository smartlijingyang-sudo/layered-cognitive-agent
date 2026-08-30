"""Build daemon turn config — gateway resolves LLM identity, machine runs SDK."""

from __future__ import annotations

from typing import Any

from lca.infrastructure.dsh.driver import DshTurnSpec
from lca.infrastructure.dsh.settings import DshSettings


def build_turn_config(
    spec: DshTurnSpec,
    settings: DshSettings,
    *,
    harness_env: dict[str, str] | None,
) -> dict[str, Any]:
    """JSON-serializable turn config for ``daemon_worker`` on the machine."""
    cfg: dict[str, Any] = {
        "prompt": spec.prompt,
        "session_id": spec.session_id,
        "cwd": spec.cwd,
        "session_root": spec.session_root,
        "provider": settings.provider,
        "model": settings.resolved_model(),
        "request_timeout_seconds": settings.request_timeout_seconds,
    }
    if harness_env:
        cfg["harness_env"] = dict(harness_env)
    api_key = settings.resolved_api_key()
    if api_key:
        cfg["api_key"] = api_key
    base_url = settings.resolved_base_url()
    if base_url:
        cfg["base_url"] = base_url
    max_tokens = settings.resolved_max_tokens()
    if max_tokens is not None:
        cfg["max_tokens"] = max_tokens
    cordis = settings.resolved_cordis()
    if cordis is not None:
        cfg["cordis"] = cordis
    return cfg
