from __future__ import annotations

from typing import Any

import pytest

from lca.application.harness_bridge import (
    MissingAgentLoopProviderError,
    build_live_agent,
)


class _Context:
    def __init__(self, values: dict[str, object]) -> None:
        self._values = values

    def inject(self, key: str) -> object:
        if key not in self._values:
            raise KeyError(key)
        return self._values[key]


def test_build_live_agent_rejects_missing_cordis_context() -> None:
    with pytest.raises(MissingAgentLoopProviderError, match="booted Cordis context"):
        build_live_agent(object(), object(), "agent-1", None)


def test_build_live_agent_rejects_missing_loop_provider() -> None:
    with pytest.raises(MissingAgentLoopProviderError, match="provide 'agent_loop'"):
        build_live_agent(object(), object(), "agent-1", None, _Context({}))


def test_build_live_agent_uses_declared_loop_provider() -> None:
    captured: dict[str, Any] = {}
    expected = object()

    def build(
        store: object,
        inbox: object,
        identity_id: str,
        options: dict[str, Any] | None,
        cordis_ctx: object,
    ) -> object:
        captured.update(
            store=store,
            inbox=inbox,
            identity_id=identity_id,
            options=options,
            cordis_ctx=cordis_ctx,
        )
        return expected

    store = object()
    inbox = object()
    ctx = _Context({"agent_loop": build})

    assert build_live_agent(store, inbox, "agent-1", {"max_steps": 3}, ctx) is expected
    assert captured == {
        "store": store,
        "inbox": inbox,
        "identity_id": "agent-1",
        "options": {"max_steps": 3},
        "cordis_ctx": ctx,
    }
