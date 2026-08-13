"""wire.py is the SSOT; generated TS must match item for item."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from gateway.runs.wire import WIRE, resolve

_PATCH = Path("deploy/lobehub/patches/runtime/lca_run_driver.py")


def test_resolve_execute_code() -> None:
    assert resolve("execute_code") == ("lobe-cloud-sandbox", "executeCode")


def test_unknown_tool_returns_none() -> None:
    assert resolve("not_a_real_tool") is None


def test_wire_has_only_resolve_function() -> None:
    tree = ast.parse(Path("gateway/runs/wire.py").read_text(encoding="utf-8"))
    defs = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert defs == ["resolve"]


def test_generated_ts_wire_matches_python() -> None:
    from deploy.lobehub.patches.runtime.lca_run_driver import render_wire_ts

    parsed = _parse_ts_wire(render_wire_ts(WIRE))
    assert parsed == {name: list(coords) for name, coords in WIRE.items()}


def test_patch_source_embeds_generated_table() -> None:
    from deploy.lobehub.patches.runtime.lca_run_driver import render_wire_ts

    source = _PATCH.read_text(encoding="utf-8")
    assert "/* __WIRE__ */" in source
    rendered = render_wire_ts(WIRE)
    assert "execute_code" in rendered
    assert rendered.count("lobe-cloud-sandbox") >= 1


def _parse_ts_wire(text: str) -> dict[str, list[str]]:
    pattern = re.compile(
        r"""['"]([A-Za-z0-9_]+)['"]\s*:\s*\[\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]"""
    )
    return {name: [ident, api] for name, ident, api in pattern.findall(text)}
