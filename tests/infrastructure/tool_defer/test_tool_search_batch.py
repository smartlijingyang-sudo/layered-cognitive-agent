from __future__ import annotations

import pytest

from lca.contracts.models.cognition.tool_defer import DeferMode
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import ToolDeferSession, set_current_defer_session
from lca.infrastructure.tool_defer.tool_search import ToolSearchTool


class FakeTool:
    def __init__(self, name: str, namespace: str) -> None:
        self.name = name
        self.namespace = namespace
        self.description = f"fake {name}"
        self.parameters = {"type": "object", "properties": {}}

    async def execute(self, args):
        return {}


@pytest.mark.asyncio
async def test_tool_search_batch_loading() -> None:
    policy = DeferPolicy.default()
    session = ToolDeferSession(policy)
    tools = (
        FakeTool("tool_search", "core"),
        FakeTool("readFile", "file"),
        FakeTool("memory_search", "memory"),
    )
    session.update_turn(tools)
    token = set_current_defer_session(session)
    try:
        searcher = ToolSearchTool()
        obs = await searcher.execute({"namespaces": ["file", "memory"]})
        assert obs.success is True
        assert "file" in session.loaded_namespaces
        assert "memory" in session.loaded_namespaces
        assert len(obs.payload["tools"]) == 2
    finally:
        session._loaded.clear()
        from lca.infrastructure.tool_defer.session import reset_current_defer_session

        reset_current_defer_session(token)


def test_missing_namespace_parks_under_unknown() -> None:
    # 2026-10-01 契约变更（run_893fac68dbda：6 个 run 因空 namespace 0-step
    # 死亡）：update_turn 不再 raise，而是把工具归入 "unknown" 伪 namespace
    #（DEFERRED，发现层面 fail-closed）并记 warning；fail-fast 移到
    # ToolsService.register（wiring time）。
    policy = DeferPolicy.default()
    session = ToolDeferSession(policy)

    class BadTool:
        def __init__(self) -> None:
            self.name = "bad"
            self.description = "bad"
            self.parameters: dict[str, str] = {}

        async def execute(self, args):
            return {}

    session.update_turn((BadTool(),))  # type: ignore[arg-type]  # 不得 raise
    (ns,) = session.namespaces
    assert ns.name == "unknown"
    assert ns.mode is DeferMode.DEFERRED
    assert "bad" in ns.tool_names


def test_invalid_namespace_fails_fast() -> None:
    # 声明了但不在 taxonomy 里的 namespace 字符串：策略配置错误，
    # fail-fast（ADR-0256 B2）。与"缺失 namespace"的 fail-soft 区分。
    policy = DeferPolicy.default()
    session = ToolDeferSession(policy)
    with pytest.raises(ValueError, match="namespace"):
        session.update_turn((FakeTool("bad", "invalid_domain"),))
