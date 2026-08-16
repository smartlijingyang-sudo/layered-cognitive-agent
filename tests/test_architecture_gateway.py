"""Architecture boundary guard for the command gateway & session routes.

The gateway layer must NOT import from concrete cognitive/runtime/agent
layers (layer1_cognitive / layer2_runtime / layer3_agent). It only sees
the harness contracts and the facade protocols. (N4 constraint)
"""

from __future__ import annotations

import ast
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_MODULES = {"layer1_cognitive", "layer2_runtime", "layer3_agent"}
GUARDED_FILES = (
    "lca/harness/command/gateway.py",
    "lca/plugins/gateway_starlette/session_routes.py",
)


def _check_file(relative_path: str) -> None:
    source = (_ROOT / relative_path).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in FORBIDDEN_MODULES:
                    assert forbidden not in alias.name, (
                        f"{relative_path} must not import {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for forbidden in FORBIDDEN_MODULES:
                assert forbidden not in module, (
                    f"{relative_path} must not import from {module}"
                )


def test_gateway_no_concrete_import() -> None:
    """CommandGateway module must not import layer1/layer2/layer3."""
    _check_file("lca/harness/command/gateway.py")


def test_session_routes_no_concrete_import() -> None:
    """session_routes.py must not import layer1/layer2/layer3."""
    _check_file("lca/plugins/gateway_starlette/session_routes.py")
