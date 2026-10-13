"""RA-136: model identity in debug/telemetry output comes from the declared seam.

Both ``cmd_debug_credentials`` (driver_debug) and the reasoner ``credentials``
plugin previously probed the private ``_model`` attribute, which returns None on
``MockLLMAdapter`` even though the declared ``LLMAdapter.model_name`` (RA-106
protocol seam) returns ``"mock-llm"``. These tests pin the declared-seam
behavior end to end: a mock-backed resolve must report "mock-llm", never None.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.infrastructure.cli.commands.runs import driver_debug
from lca.infrastructure.llm_adapter import MockLLMAdapter


class _FakeResolver:
    """Stand-in for ProductionLLMResolver: always resolves the mock adapter."""

    def __init__(self, **kwargs: Any) -> None:
        pass

    def resolve(self) -> MockLLMAdapter:
        return MockLLMAdapter()


@pytest.fixture()
def _mock_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    import lca.infrastructure.llm.resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "ProductionLLMResolver", _FakeResolver)
    monkeypatch.setenv("LLM_API_KEY", "dummy")


def test_debug_credentials_reports_mock_llm(
    _mock_resolver: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        driver_debug,
        "emit_report",
        lambda report, **kwargs: captured.update(report),
    )
    driver_debug.cmd_debug_credentials(json_mode=True)
    adapter = captured["adapter"]
    assert adapter["resolved"] is True
    assert adapter["type"] == "MockLLMAdapter"
    assert adapter["model"] == "mock-llm"


class _FakeCtx:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict[str, Any]]] = []
        self.provided: dict[str, Any] = {}

    def emit(self, name: str, payload: dict[str, Any]) -> None:
        self.emitted.append((name, payload))

    def provide(self, name: str, value: Any) -> None:
        self.provided[name] = value


async def test_reasoner_credentials_served_reports_mock_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lca.infrastructure.llm.config as config_mod
    import lca.infrastructure.llm.resolver as resolver_mod
    from lca.plugins.think.reasoner import credentials as creds

    monkeypatch.setattr(resolver_mod, "ProductionLLMResolver", _FakeResolver)
    monkeypatch.setattr(config_mod, "llm_credentials", lambda: ("dummy", None, None))

    ctx = _FakeCtx()
    # @plugin wraps setup in a Plugin object; .setup is the raw coroutine.
    await creds.setup.setup(ctx, creds.Config())  # type: ignore[arg-type]
    served = [
        payload
        for name, payload in ctx.emitted
        if name == "phase_think_reasoner_credentials.served"
    ]
    assert len(served) == 1
    assert served[0]["adapter_model"] == "mock-llm"
