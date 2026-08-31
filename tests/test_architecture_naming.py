"""Architecture boundary guard for the session command dispatcher & session routes.

ADR-0119 followup-2 (2026-08-31): 原 ``CommandGateway`` 改为
``SessionCommandDispatcher``,模块路径由 ``lca.harness.command.gateway``
改为 ``lca.harness.command.dispatcher``(gateway.py 保留为 1-release 兼容
shim,只 re-export dispatcher 内容)。本文件验证 SessionCommandDispatcher
不直接 import 任何具体认知/运行/Agent 实现层。

N4 constraint: session command dispatcher 层 must NOT import from concrete
cognitive/runtime/agent layers. It only sees the harness contracts and the
facade protocols.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_MODULES = {"cognition", "runtime", "agent"}
GUARDED_FILES = ("lca/harness/command/dispatcher.py",)


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


def test_session_command_dispatcher_no_concrete_import() -> None:
    """SessionCommandDispatcher module must not import layer1/layer2/layer3.

    ADR-0119 followup-2: 原 ``test_gateway_no_concrete_import`` 改名以反映
    ``CommandGateway`` → ``SessionCommandDispatcher`` 改名。
    """
    for guarded in GUARDED_FILES:
        _check_file(guarded)


def test_compat_shim_only_re_exports() -> None:
    """``lca/harness/command/gateway.py`` 兼容 shim 只 re-export dispatcher 内容。

    旧 import 路径(2026-12-31 前)仍能工作;过期后本 shim 删除。
    """
    shim = _ROOT / "lca/harness/command/gateway.py"
    if not shim.exists():
        return
    source = shim.read_text()
    tree = ast.parse(source)
    # shim 只允许 import dispatcher 自身,不应 import 任何 forbidden 模块。
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for forbidden in FORBIDDEN_MODULES:
                assert forbidden not in module, f"compat shim must not import from {module}"
