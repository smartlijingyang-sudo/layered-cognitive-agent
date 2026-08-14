"""wire.py is the SSOT; generated TS must match item for item."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from gateway.runs.wire import WIRE, resolve


def test_resolve_execute_code() -> None:
    assert resolve("executeCode") == ("lobe-cloud-sandbox", "executeCode")


def test_unknown_tool_returns_none() -> None:
    assert resolve("not_a_real_tool") is None


def test_wire_has_only_resolve_function() -> None:
    tree = ast.parse(Path("gateway/runs/wire.py").read_text(encoding="utf-8"))
    defs = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert defs == ["resolve"]


def test_generated_ts_wire_matches_python() -> None:
    from deploy.lobehub.patches.runtime.lca_run_driver import render_wire_ts

    rendered = render_wire_ts(WIRE)
    assert rendered.startswith("/** Generated from gateway.runs.wire.WIRE.")
    assert "export const WIRE" in rendered
    parsed = _parse_ts_wire(rendered)
    assert parsed == {name: list(coords) for name, coords in WIRE.items()}


def _parse_ts_wire(text: str) -> dict[str, list[str]]:
    pattern = re.compile(
        r"""['"]([A-Za-z0-9_]+)['"]\s*:\s*\[\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]"""
    )
    return {name: [ident, api] for name, ident, api in pattern.findall(text)}
