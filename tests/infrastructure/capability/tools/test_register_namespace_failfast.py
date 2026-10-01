"""ToolsService.register() namespace fail-fast 回归（ADR-0256）。

漏声明 namespace 的工具在注册时（wiring time）就被拒绝，
而不是在 run 中途 ToolDeferSession.update_turn 里爆炸。
"""
from __future__ import annotations

from typing import Any

import pytest

from lca.infrastructure.capability.tools.tools import ToolsService


class FakeTool:
    def __init__(self, name: str, namespace: str = "") -> None:
        self.name = name
        self.namespace = namespace
        self.description = f"fake {name}"
        self.parameters = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}


def test_register_rejects_missing_namespace():
    svc = ToolsService()
    with pytest.raises(ValueError, match="namespace"):
        svc.register(FakeTool("no_ns_tool"))


def test_register_accepts_declared_namespace():
    svc = ToolsService()
    tool = FakeTool("ok_tool", namespace="core")
    svc.register(tool)
    assert svc.get("ok_tool") is tool
