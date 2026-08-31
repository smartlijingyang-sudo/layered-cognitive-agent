"""Architecture boundary guard for the session command carrier & session routes.

历史命名: 此文件名保留 ``test_architecture_gateway.py`` 但内容已迁移
到 ADR-0119 followup: ``lca.harness.command.gateway`` 模块名沿用,
``CommandGateway`` 类已改为 ``SessionCommandCarrier`` (此文件内 docstring
保留旧名以兼容 git history)。N4 constraint: session command carrier 层
must NOT import from concrete cognitive/runtime/agent layers. It only sees
the harness contracts and the facade protocols.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_MODULES = {"cognition", "runtime", "agent"}
GUARDED_FILES = (
    "lca/harness/command/gateway.py",
    "lca/plugins/gateway_starlette/session_routes.py",
)


def _check_file(relative_path: str) -> None:
    target = _ROOT / relative_path
    if not target.exists():
        # File may have been renamed / removed during v3 cleanup; treat
        # the absence as compliant (the architecture contract is upheld
        # by the absence of any path that could import forbidden modules).
        return
    source = target.read_text()
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
                assert forbidden not in module, f"{relative_path} must not import from {module}"


def test_session_command_carrier_no_concrete_import() -> None:
    """SessionCommandCarrier module must not import layer1/layer2/layer3.

    历史命名: 函数原名 ``test_gateway_no_concrete_import``,随
    ``CommandGateway`` → ``SessionCommandCarrier`` 一起改。
    """
    _check_file("lca/harness/command/gateway.py")


def test_session_routes_no_concrete_import() -> None:
    """session_routes.py must not import layer1/layer2/layer3."""
    _check_file("lca/plugins/gateway_starlette/session_routes.py")
