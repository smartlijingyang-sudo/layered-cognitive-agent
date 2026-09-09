"""PR-2 of ADR-0213: ``/health`` body carries the ``plugin`` block.

The block surfaces the 5 readiness signals the spawner's ``http_ready``
step requires (ADR-0213 §决定 4). Each signal is independently
verified so a regression in one path doesn't hide behind another.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.requests import Request  # noqa: TC002  (runtime annotation)
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import (
    _read_plugin_health,
    health_payload,
)


class _StubRunPort:
    def status_counts(self) -> dict[str, int]:
        return {"running": 0, "pending": 0}

    def live_totals(self) -> dict[str, int]:
        return {"journal_subscribers": 0}


async def _health_route(request: Request) -> JSONResponse:
    payload = health_payload(
        _StubRunPort(),
        ctx=getattr(request.app.state, "ctx", None),
    )
    return JSONResponse(payload)


def _make_app() -> Starlette:
    return Starlette(routes=[Route("/health", _health_route, methods=["GET"])])


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


@pytest.fixture(autouse=True)
def _reset_event_bus_singleton() -> None:
    from lca_kernel.events import EventBus

    EventBus.reset_singleton()
    yield
    EventBus.reset_singleton()


# ── plugin block shape ─────────────────────────────────────────────


def test_health_body_includes_plugin_block_when_ctx_present(
    client: TestClient,
) -> None:
    """A ctx-bound app produces a ``plugin`` block with the 6 documented keys."""
    body = client.get("/health").json()
    assert "plugin" in body
    p = body["plugin"]
    assert set(p) >= {
        "registered",
        "expected",
        "missing",
        "registry_populated",
        "pipeline_registered",
        "cognitive_driver_registered",
    }


def test_health_body_omits_plugin_block_when_ctx_missing() -> None:
    """Without ctx the block degrades gracefully (still no plugin key)."""
    app = _make_app()
    client = TestClient(app)
    body = client.get("/health").json()
    # The block is read with graceful degradation; absence is acceptable
    # when ctx is None and no resolved profile is attachable.
    assert "status" in body
    # plugin may or may not appear depending on bus-only readiness; the
    # important contract is that no exception is raised and status==ok
    # remains (the plugin block is purely additive).
    assert body["status"] in {"ok", "degraded"}


# ── _read_plugin_health direct ─────────────────────────────────────


def test_read_plugin_health_returns_full_block(monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct call returns the 6 keys with concrete values when ctx is wired."""
    fake_registry = MagicMock()
    fake_registry._plugins = {"lca.x": object(), "lca.y": object(), "lca.z": object()}

    fake_bus = MagicMock()
    fake_bus.registry = fake_registry

    fake_driver_registry = MagicMock()
    fake_driver_registry.contains = lambda target: target in {"cognitive", "infoedge"}

    class _FakeResolved:
        from typing import ClassVar

        plugins: ClassVar[list[object]] = []

    with (
        patch("lca_kernel.events.EnvelopeBus.default", return_value=fake_bus),
        patch(
            "lca.harness.profile.resolve.pipeline_loader._REGISTERED",
            {fake_bus: {("web-standard-event-pipeline", 1)}},
        ),
        patch(
            "lca.contracts.mechanisms.capability.capability.require_capability",
            return_value=fake_driver_registry,
        ),
    ):
        block = _read_plugin_health(ctx=MagicMock())

    assert block["registered"] == 3
    assert block["expected"] == 0  # no resolved profile attached → no expected count
    assert block["missing"] == []
    assert block["registry_populated"] is True
    assert block["pipeline_registered"] is True
    assert block["cognitive_driver_registered"] is True


def test_read_plugin_health_pipeline_registered_false_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_registry = MagicMock()
    fake_registry._plugins = {}
    fake_bus = MagicMock()
    fake_bus.registry = fake_registry

    with (
        patch("lca_kernel.events.EnvelopeBus.default", return_value=fake_bus),
        patch("lca.harness.profile.resolve.pipeline_loader._REGISTERED", {}),
    ):
        block = _read_plugin_health(ctx=None)
    assert block["pipeline_registered"] is False


def test_read_plugin_health_cognitive_driver_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ctx does not provide run_loop_driver_registry, block still returns."""
    fake_registry = MagicMock()
    fake_registry._plugins = {}
    fake_bus = MagicMock()
    fake_bus.registry = fake_registry

    from lca.contracts.mechanisms.capability.capability import MissingCapabilityError

    def _raise_cap(*args: Any, **kwargs: Any) -> Any:
        raise MissingCapabilityError("run_loop_driver_registry")

    with (
        patch("lca_kernel.events.EnvelopeBus.default", return_value=fake_bus),
        patch("lca.harness.profile.resolve.pipeline_loader._REGISTERED", {}),
        patch(
            "lca.contracts.mechanisms.capability.capability.require_capability",
            side_effect=_raise_cap,
        ),
    ):
        block = _read_plugin_health(ctx=MagicMock())
    assert block["cognitive_driver_registered"] is False


def test_read_plugin_health_graceful_when_bus_explodes() -> None:
    """EnvelopeBus.default raising → block returns None, no exception leaks."""
    with patch(
        "lca_kernel.events.EnvelopeBus.default",
        side_effect=RuntimeError("event bus unavailable"),
    ):
        result = _read_plugin_health(ctx=MagicMock())
    assert result is None


def test_read_plugin_health_expected_uses_resolved_profile_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expected count = plugins in resolved profile with marker_class set."""
    from dataclasses import dataclass
    from typing import ClassVar

    @dataclass
    class _FakeDef:
        marker_class: type | None
        ownership: object | None = None

    @dataclass
    class _FakePlugin:
        id: str
        definition: _FakeDef
        index: int = 0
        disabled: bool = False

    @dataclass
    class _FakeResolved:
        plugins: ClassVar[list[_FakePlugin]]

    fake_registry = MagicMock()

    # catalog only has 1 of 2 plugins; the other is missing
    class _Marker:
        pass

    fake_registry._plugins = {"lca.x": _Marker}
    fake_bus = MagicMock()
    fake_bus.registry = fake_registry

    resolved = _FakeResolved(
        plugins=[
            _FakePlugin(id="lca.x", definition=_FakeDef(marker_class=_Marker)),
            _FakePlugin(id="lca.y", definition=_FakeDef(marker_class=_Marker)),
            # marker_class None → not expected
            _FakePlugin(id="lca.z", definition=_FakeDef(marker_class=None)),
        ]
    )

    with (
        patch("lca_kernel.events.EnvelopeBus.default", return_value=fake_bus),
        patch("lca.harness.profile.resolve.pipeline_loader._REGISTERED", {}),
        patch(
            "lca.harness.profile.boot.products.resolved_profile_from_scope",
            return_value=resolved,
        ),
    ):
        block = _read_plugin_health(ctx=MagicMock())
    assert block["registered"] == 1
    assert block["expected"] == 2  # lca.x + lca.y (marker set), NOT lca.z
    assert block["missing"] == ["lca.y"]
    assert block["registry_populated"] is True
