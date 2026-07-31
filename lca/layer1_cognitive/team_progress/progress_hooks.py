"""Compat re-export — progress_injection_hook removed (derive via as_prompt_text)."""

from __future__ import annotations

from typing import Any

from lca.contracts.state import AgentState
from lca.layer1_cognitive.member_status.hooks import track_member_status_hook

ledger_tracking_hook = track_member_status_hook


async def progress_injection_hook(event_name: str, state: AgentState, **kwargs: Any) -> None:
    """No-op: Reasoner reads ``member_status.as_prompt_text()`` directly.

    Kept as a deprecated stub so old register sites do not crash.
    """
    del event_name, state, kwargs
