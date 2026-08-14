"""LobeHub stack CLI — YAML SSOT, route catalog, command steps, restart delta."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from deploy.lobehub.stack.config import DEFAULT_YAML, StackConfig, SurfaceMeta
from deploy.lobehub.stack.inspect import (
    DiscoveredRoute,
    bind_surfaces,
    iter_app_routes,
    newer_files,
)
from deploy.lobehub.stack.report import render_report
from deploy.lobehub.stack.types import (
    BoundSurface,
    Check,
    ProcessSnapshot,
    RestartDelta,
    Section,
    StackReport,
    Status,
)
from gateway.app import create_app


def test_default_yaml_loads() -> None:
    data = yaml.safe_load(DEFAULT_YAML)
    config = StackConfig.model_validate(data)
    assert "restart-gateway" in config.commands
    assert "status" in config.commands
    assert config.gateway.port == 8765
    assert any(s.id == "devices" for s in config.surfaces)


def test_committed_stack_yaml_matches_models() -> None:
    path = Path("deploy/lobehub/stack.yaml")
    config = StackConfig.from_yaml(path)
    assert config.commands["restart-gateway"].steps[0] == "gateway.snapshot"
    assert "gateway.restart" in config.commands["restart-gateway"].steps


def test_catalog_covers_every_app_route() -> None:
    app = create_app()
    routes = iter_app_routes(app)
    assert routes, "create_app() must expose routes"
    bound = bind_surfaces(routes, StackConfig().surfaces)
    covered = {route.path for surface in bound for route in surface.routes}
    assert {route.path for route in routes} == covered


def test_unknown_route_is_unclassified() -> None:
    routes = [DiscoveredRoute(path="/brand-new-capability", methods=("GET",), kind="http")]
    bound = bind_surfaces(
        routes,
        [SurfaceMeta(id="health", match="^/health$", title="Health", purpose="liveness")],
    )
    leftover = [surface for surface in bound if surface.id == "unclassified"]
    assert len(leftover) == 1
    assert leftover[0].routes[0].path == "/brand-new-capability"
    assert leftover[0].classified is False


def test_known_prefix_does_not_drop_sibling_paths() -> None:
    routes = [
        DiscoveredRoute(path="/runs", methods=("POST",), kind="http"),
        DiscoveredRoute(path="/runs/{run_id}/live", methods=("GET",), kind="http"),
        DiscoveredRoute(path="/health", methods=("GET",), kind="http"),
    ]
    bound = bind_surfaces(routes, StackConfig().surfaces)
    by_id = {surface.id: surface for surface in bound}
    assert {route.path for route in by_id["runs"].routes} == {
        "/runs",
        "/runs/{run_id}/live",
    }
    assert [route.path for route in by_id["health"].routes] == ["/health"]
    assert "unclassified" not in by_id


def test_every_yaml_step_is_registered() -> None:
    from deploy.lobehub.stack.cli import STEPS

    config = StackConfig.from_yaml("deploy/lobehub/stack.yaml")
    missing = [
        f"{name}:{step}"
        for name, spec in config.commands.items()
        for step in spec.steps
        if step not in STEPS
    ]
    assert missing == []


def test_newer_files_follow_watch_config(tmp_path: Path) -> None:
    watch = tmp_path / "gateway"
    watch.mkdir()
    stale = watch / "old.py"
    stale.write_text("a\n", encoding="utf-8")
    old_epoch = stale.stat().st_mtime
    fresh = watch / "new.py"
    fresh.write_text("b\n", encoding="utf-8")
    os.utime(fresh, (old_epoch + 10, old_epoch + 10))
    found = newer_files([str(watch)], since_epoch=old_epoch, glob="*.py", root=tmp_path)
    names = [path.name for path in found]
    assert "new.py" in names
    assert "old.py" not in names


def test_render_report_lists_surfaces_patches_and_delta() -> None:
    report = StackReport(
        command="restart-gateway",
        verdict="ready",
        process=ProcessSnapshot(
            pid=42,
            alive=True,
            port=8765,
            listening=True,
            public_url="http://127.0.0.1:8765",
            health={"status": "ok", "llm_available": True},
        ),
        surfaces=[
            BoundSurface(
                id="health",
                title="Health",
                purpose="liveness",
                routes=(DiscoveredRoute(path="/health", methods=("GET",), kind="http"),),
                classified=True,
                probe_status=Status.OK,
                probe_detail="200 llm=true",
            ),
            BoundSurface(
                id="unclassified",
                title="Unclassified",
                purpose="routes with no surface metadata",
                routes=(DiscoveredRoute(path="/future", methods=("GET",), kind="http"),),
                classified=False,
            ),
        ],
        sections=[
            Section(
                id="patches",
                title="patches",
                checks=(Check(name="lca_run_driver", status=Status.OK, detail="runtime · marker present"),),
            )
        ],
        delta=RestartDelta(
            reason="force",
            previous_pid=7,
            current_pid=42,
            newer_files=("gateway/app.py",),
        ),
    )
    text = render_report(report)
    assert "restart-gateway" in text
    assert "/health" in text
    assert "/future" in text
    assert "unclassified" in text.lower()
    assert "lca_run_driver" in text
    assert "gateway/app.py" in text
    assert "7" in text and "42" in text
