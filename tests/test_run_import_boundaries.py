"""Dependency graph for gateway/runs — docs/run-live.md."""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path("gateway")


def _source(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _imports(rel: str) -> list[str]:
    tree = ast.parse(_source(rel))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_live_has_no_starlette() -> None:
    assert "starlette" not in _source("runs/live.py")


def test_doctor_has_no_starlette() -> None:
    assert "starlette" not in _source("runs/doctor.py")


def test_wire_imports_no_gateway_modules() -> None:
    for name in _imports("runs/wire.py"):
        assert not name.startswith("gateway"), name


def test_execute_has_no_starlette_or_request() -> None:
    text = _source("runs/execute.py")
    assert "starlette" not in text
    assert "from starlette" not in text
    assert "import starlette" not in text


def test_ingress_does_not_import_live_or_execute() -> None:
    text = _source("runs/ingress.py")
    assert "gateway.runs.live" not in text
    assert "gateway.runs.execute" not in text


def test_live_does_not_import_wire_or_ingest() -> None:
    text = _source("runs/live.py")
    assert "gateway.runs.wire" not in text
    assert "gateway.runs.ingest" not in text
    assert "gateway.assemble" not in text


def test_api_does_not_import_app() -> None:
    text = _source("runs/api.py")
    assert "gateway.app" not in text
