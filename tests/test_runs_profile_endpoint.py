"""GET /runs/{run_id}/profile returns the boot-time profile_snapshot.json.

The tracker named ``gateway/runs/api.py``; that facade was removed
(``tests/test_run_import_boundaries.py::test_run_handler_facade_is_absent``).
The handler lives in ``gateway.runs.query_endpoints`` and is registered
on ``/runs/{run_id}/profile`` (LobeHub prefixes ``/lca-api`` at the proxy).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

if TYPE_CHECKING:
    import pytest

from gateway.runs.query_endpoints import get_run_profile
from lca.contracts.observability.run_locator import RunLocator
from lca.infrastructure.observability.run_locator_fs import FilesystemRunLocator
from lca.plugins.providers.profile_snapshot.run_boot import RunBootSnapshot


class _LocatorCtx:
    """Minimal Cordis-shaped ctx: ``require_capability`` uses ``inject``."""

    def __init__(self, locator: RunLocator) -> None:
        self._locator = locator

    def inject(self, key: str) -> object:
        if key != "run_locator":
            raise KeyError(key)
        return self._locator


def _make_app(*, ctx: object | None = None) -> Starlette:
    application = Starlette(
        routes=[Route("/runs/{run_id}/profile", get_run_profile, methods=["GET"])],
    )
    application.state.ctx = ctx
    return application


def _write_snapshot(outdir: Path, *, run_id: str) -> dict[str, Any]:
    snapshot = RunBootSnapshot()
    snapshot.write(
        run_id=run_id,
        outdir=outdir,
        plan_ref="plan-hash",
        plugins=["lca-llm", "lca-tools"],
        capabilities={"llm": True},
        control_plan={"version": "v3"},
    )
    return {
        "run_id": run_id,
        "plan_ref": "plan-hash",
        "plugins": ["lca-llm", "lca-tools"],
        "capabilities": {"llm": True},
        "control_plan": {"version": "v3"},
    }


def test_get_profile_returns_snapshot(tmp_path: Path) -> None:
    locator = FilesystemRunLocator(root=tmp_path)
    expected = _write_snapshot(locator.run_dir("r1"), run_id="r1")
    client = TestClient(_make_app(ctx=_LocatorCtx(locator)))

    resp = client.get("/runs/r1/profile")

    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "r1"
    assert "lca-llm" in data["plugins"]
    assert data == expected


def test_get_profile_404_when_missing(tmp_path: Path) -> None:
    locator = FilesystemRunLocator(root=tmp_path)
    client = TestClient(_make_app(ctx=_LocatorCtx(locator)))

    resp = client.get("/runs/nonexistent-run-id-12345/profile")

    assert resp.status_code == 404
    assert "nonexistent-run-id-12345" in resp.json()["error"]


def test_get_profile_uses_default_traces_layout_without_locator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    expected = _write_snapshot(tmp_path / "traces" / "runs" / "r1", run_id="r1")
    client = TestClient(_make_app(ctx=None))

    resp = client.get("/runs/r1/profile")

    assert resp.status_code == 200
    assert resp.json() == expected


def test_get_profile_500_when_snapshot_is_not_json(tmp_path: Path) -> None:
    locator = FilesystemRunLocator(root=tmp_path)
    path = locator.run_dir("r1") / "profile_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not-json", encoding="utf-8")
    client = TestClient(_make_app(ctx=_LocatorCtx(locator)))

    resp = client.get("/runs/r1/profile")

    assert resp.status_code == 500
    assert resp.json()["error"] == "invalid profile snapshot"


def test_catalog_registers_profile_route() -> None:
    from gateway.routes import build_routes

    paths = {route.path for route in build_routes() if hasattr(route, "path")}
    assert "/runs/{run_id}/profile" in paths
