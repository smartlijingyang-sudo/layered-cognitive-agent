"""ToolDeferSession.update_turn fail-soft 回归（2026-10-01 run_893fac68dbda）。

- wrapper 吞掉 namespace（旧 bug）时 run 不得 0-step 死亡：wrapper
  经 __getattr__ 透传 namespace，update_turn 正常分组。
- namespace 缺失/未知时：归入 "unknown" 伪 namespace（DEFERRED，
  发现层面 fail-closed），只记 warning，绝不 raise。
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from lca.contracts.models.cognition.tool_defer import DeferMode
from lca.infrastructure.auto_review.wrapped_tool import AutoReviewWrappedTool
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import ToolDeferSession


class FakeTool:
    def __init__(self, name: str, namespace: str = "") -> None:
        self.name = name
        self.namespace = namespace
        self.description = f"fake {name}"
        self.parameters = {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}


def _session() -> ToolDeferSession:
    return ToolDeferSession(DeferPolicy())


def test_wrapped_tool_delegates_namespace():
    inner = FakeTool("web_search", namespace="web")
    wrapped = AutoReviewWrappedTool(inner, gate=object())
    assert getattr(wrapped, "namespace", "") == "web"
    session = _session()
    session.update_turn([wrapped])
    assert [ns.name for ns in session.namespaces] == ["web"]


def test_missing_namespace_parks_under_unknown(caplog):
    tool = FakeTool("mystery_tool")  # namespace == ""
    session = _session()
    with caplog.at_level(logging.WARNING, logger="lca.infrastructure.tool_defer.session"):
        session.update_turn([tool])  # 不得 raise
    assert [ns.name for ns in session.namespaces] == ["unknown"]
    ns = session.namespaces[0]
    assert ns.mode is DeferMode.DEFERRED
    assert "mystery_tool" in ns.tool_names
    assert any("mystery_tool" in r.message for r in caplog.records)


def test_unknown_namespace_string_fails_fast():
    # 声明了但不在 policy 描述表里的 namespace = 分类体系违规/策略配错，
    # 按 ADR-0256 B2 fail-fast（默认 policy 下生产环境不会触发）。
    tool = FakeTool("rogue", namespace="not_a_real_ns")
    session = _session()
    with pytest.raises(ValueError, match="namespace"):
        session.update_turn([tool])


def test_mixed_turn_groups_correctly():
    tools = [
        FakeTool("tool_search", namespace="core"),
        FakeTool("no_ns"),
    ]
    session = _session()
    session.update_turn(tools)
    names = [ns.name for ns in session.namespaces]
    assert "core" in names and "unknown" in names
