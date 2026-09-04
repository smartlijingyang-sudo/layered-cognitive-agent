"""PR-4: /health handler exposes ``event_bus`` field + PersistenceWorker observability.

The health payload now bundles EventBus delivery counters and, when loaded,
PersistenceWorker fsync policy + queue depth. ``dropped_total > 0`` flips
``status`` to ``degraded`` without breaking readiness. The field is omitted
when EventBus is unavailable (graceful degradation).
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request  # noqa: TC002  (runtime annotation)
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from lca.plugins.transport.webserver.handlers.runs.api.query_endpoints import (
    _read_event_bus_health,
    health_payload,
)


class _StubRunPort:
    """Minimal RunPort: health_payload only touches status_counts + live_totals."""

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


# ── helper fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


@pytest.fixture(autouse=True)
def _reset_event_bus_singleton() -> None:
    """Avoid cross-test bleed: each test gets a fresh EventBus instance."""
    from lca_kernel.events import EventBus

    EventBus.reset_singleton()
    yield
    EventBus.reset_singleton()


# ── /health handler ──────────────────────────────────────────────────────


def test_health_payload_includes_event_bus(client: TestClient) -> None:
    """GET /health returns 200 + JSON containing the event_bus subfield."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "event_bus" in body
    eb = body["event_bus"]
    assert set(eb) >= {
        "published_total",
        "persisted_total",
        "delivered_total",
        "dropped_total",
        "fsync_policy",
    }


def test_health_payload_event_bus_dropped_total_zero_initially(
    client: TestClient,
) -> None:
    """On a fresh process the counters are all zero + status stays ``ok``."""
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["event_bus"]["published_total"] == 0
    assert body["event_bus"]["persisted_total"] == 0
    assert body["event_bus"]["delivered_total"] == 0
    assert body["event_bus"]["dropped_total"] == 0


def test_health_payload_event_bus_dropped_sets_degraded(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """dropped_total > 0 → status flips to ``degraded`` (not blocking readiness)."""
    fake_snapshot = {
        "team.delegation.cache_hit": {
            "published": 5,
            "persisted": 0,
            "delivered": 0,
            "dropped": 5,
        }
    }

    def _fake_snapshot(self: Any) -> dict[str, dict[str, int]]:
        return fake_snapshot

    monkeypatch.setattr("lca_kernel.events.EventBus.delivery_snapshot", _fake_snapshot)
    # Force the lazy lookup inside _read_event_bus_health to use the patched class.
    monkeypatch.setattr("lca_kernel.events.bus.EventBus.delivery_snapshot", _fake_snapshot)

    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["event_bus"]["dropped_total"] == 5
    assert body["event_bus"]["published_total"] == 5
    # Response still 200; degraded is a label, not a readiness gate.
    assert client.get("/health").status_code == 200


def test_health_payload_event_bus_missing_graceful(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """If EventBus.delivery_snapshot raises, health still returns the core shape."""

    def _boom(self: Any) -> dict[str, dict[str, int]]:
        raise RuntimeError("event bus unavailable")

    monkeypatch.setattr("lca_kernel.events.bus.EventBus.delivery_snapshot", _boom)

    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "runs" in body
    assert "live" in body
    assert "event_bus" not in body


# ── _read_event_bus_health direct ─────────────────────────────────────────


def test_read_event_bus_health_returns_dict_on_fresh_process() -> None:
    """Direct call returns a dict with the five required keys + zero totals."""
    result = _read_event_bus_health()
    assert result is not None
    assert result["published_total"] == 0
    assert result["persisted_total"] == 0
    assert result["delivered_total"] == 0
    assert result["dropped_total"] == 0
    # fsync_policy reads from PersistenceWorker (PR-2 landed); default FsyncPolicy.BATCH.
    assert result["fsync_policy"] in {"batch", "n/a"}  # "n/a" only if PersistenceWorker failed to import


def test_read_event_bus_health_swallows_persistence_worker_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PersistenceWorker module absence must not poison the snapshot."""
    # Pre-condition: persistence module does not exist on this branch (PR-2 pending).
    import builtins

    real_import = builtins.__import__

    def _guarded(name: str, *args: Any, **kwargs: Any):
        if name == "lca_kernel.events.persistence" or name.endswith(".events.persistence"):
            raise ImportError("simulated PR-2 not merged")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guarded)

    result = _read_event_bus_health()
    assert result is not None
    assert result["fsync_policy"] == "n/a"
    assert "queue_depth" not in result
