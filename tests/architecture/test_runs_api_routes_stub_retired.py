"""Structural tests: the retired ``routes`` stub is gone.

ADR-0163 kept a sibling re-export stub only for legacy ``mock.patch``
strings. All references migrated onto the real submodules; the stub is
deleted. Tests must patch ``...api.<sub>.X`` directly.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_routes_stub_file_is_deleted() -> None:
    stub = (
        REPO
        / "lca"
        / "plugins"
        / "transport"
        / "webserver"
        / "handlers"
        / "runs"
        / "api"
        / "routes.py"
    )
    assert not stub.exists()


def test_api_init_does_not_reexport_routes() -> None:
    import lca.plugins.transport.webserver.handlers.runs.api as api

    assert "routes" not in api.__all__
    assert hasattr(api, "query_endpoints")
    assert not hasattr(api, "routes")


def test_api_submodules_import_cleanly() -> None:
    from lca.plugins.transport.webserver.handlers.runs.api import (  # noqa: F401
        attachment_staging,
        command_endpoints,
        file_reference_parsing,
        query_endpoints,
    )

    assert callable(command_endpoints.create_run)
    assert callable(query_endpoints.get_run)


def test_no_production_module_imports_routes_stub() -> None:
    import re

    violations: list[str] = []
    for path in (REPO / "lca").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"handlers\.runs\.api\.routes", text):
            violations.append(str(path))
    assert violations == [], f"routes stub still referenced: {violations}"
