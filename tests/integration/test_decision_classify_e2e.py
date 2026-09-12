"""E2E test for ADR-0221 — ``concept.decision.classify`` 2-node graph.

加载 ``bundles/concept/decision_classify.yaml`` 并通过 ``PlanInterpreter.run``
完整执行。回归目标:

1. 2 节点图(``decision.parse.response`` + ``decision.compose.action``)端到端跑通
2. ``decision`` 端口非 ``None``
3. ``action_type`` 与输入 ``LLMResponse`` 形态匹配(USE_TOOL / DELEGATE / RESPOND / 空响应 fallback 四态)
4. close-out 投影可消费最终 ``decision``
"""

from __future__ import annotations

from pathlib import Path

import yaml as _yaml

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    NativeToolCall,
)
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.graph.binding import BindingKind
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lifter import lift_graph_spec
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.strategies.node_executor_strategy import (
    NodeExecutorStrategy,
)
from lca.framework.graph.strategy_registry import (
    StrategyRegistry,
)
from lca.plugins.concept.decision_classify.compose_action import (
    DecisionComposeActionExecutor,
)
from lca.plugins.concept.decision_classify.parse_tool_calls import (
    DecisionParseResponseExecutor,
)


def _registry_with_executors() -> StrategyRegistry:
    """Build a StrategyRegistry with NODE_EXECUTOR strategy wired to our 2 executors."""
    registry = StrategyRegistry()

    lookup: dict[str, object] = {
        "decision.parse.response": DecisionParseResponseExecutor(),
        "decision.compose.action": DecisionComposeActionExecutor(),
    }

    def executor_lookup(*, binding: BindingKind, node_id: str, region: str | None):
        if binding is not BindingKind.NODE_EXECUTOR:
            raise KeyError(f"unexpected binding {binding!r} in e2e test")
        if node_id not in lookup:
            raise KeyError(f"no executor for node_id={node_id!r}")
        return lookup[node_id]

    registry.register(NodeExecutorStrategy(executor_lookup=executor_lookup))
    return registry


def _load_decision_classify_plan():
    """Load and lift the production bundle yaml."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    spec = _yaml.safe_load(
        (repo_root / "bundles" / "concept" / "decision_classify.yaml").read_text(encoding="utf-8")
    )
    # lift_graph_spec 校验 exactly-one entry;bundle yaml 不写 entry: 字段,
    # 由 outer graph (think.yaml / reasoning_turn.yaml) 通过 sub_spec_ref
    # binding 传入。这里直接指定 entry_node 让 plan 可独立运行。
    spec = dict(spec)
    spec.setdefault("entry", "decision.parse.response")
    plan = lift_graph_spec(spec)
    return plan


def _run_graph(response: LLMResponse) -> dict[str, object]:
    """Execute the concept.decision.classify plan and return merged output ports."""
    plan = _load_decision_classify_plan()
    registry = _registry_with_executors()
    interpreter = PlanInterpreter(registry=registry)
    ports = PortRegistry()
    ports.set_outer_input({"response": response})
    import asyncio

    result = asyncio.run(interpreter.run(plan, port_registry=ports))
    return dict(result.output)


def test_graph_has_two_nodes_and_one_edge() -> None:
    """Bundles yaml 拓扑契约:2 节点 + 1 edge。"""
    plan = _load_decision_classify_plan()
    assert len(plan.nodes) == 2
    assert {n.id for n in plan.nodes} == {
        "decision.parse.response",
        "decision.compose.action",
    }
    assert len(plan.edges) == 1
    edge = plan.edges[0]
    assert edge.source == "decision.parse.response"
    assert edge.target == "decision.compose.action"


def test_graph_run_produces_use_tool_decision() -> None:
    response = LLMResponse(
        text="",
        finish_reason="tool_calls",
        tool_calls=[NativeToolCall(call_id="c1", name="listFiles", arguments={})],
    )
    output = _run_graph(response)
    decision = output["decision"]
    assert isinstance(decision, Decision)
    assert decision.action_type == ActionType.USE_TOOL.value
    assert len(decision.tool_calls) == 1
    assert decision.tool_calls[0].tool_name == "listFiles"


def test_graph_run_produces_delegate_decision() -> None:
    response = LLMResponse(
        text="",
        finish_reason="tool_calls",
        tool_calls=[
            NativeToolCall(
                call_id="c1",
                name="delegate",
                arguments={"subtask": "sub", "target_role": "researcher"},
            )
        ],
    )
    output = _run_graph(response)
    decision = output["decision"]
    assert decision.action_type == ActionType.DELEGATE.value
    assert len(decision.delegations) == 1
    assert decision.delegations[0].subtask == "sub"


def test_graph_run_produces_respond_decision() -> None:
    response = LLMResponse(text="完成。", finish_reason="stop")
    output = _run_graph(response)
    decision = output["decision"]
    assert decision.action_type == ActionType.RESPOND.value
    assert decision.response_text == "完成。"


def test_graph_run_empty_response_falls_back_to_respond() -> None:
    response = LLMResponse(text="", finish_reason="stop")
    output = _run_graph(response)
    decision = output["decision"]
    assert decision.action_type == ActionType.RESPOND.value
    assert decision.confidence == 0.0


def test_graph_run_with_leaked_text_decision_compose_unaffected() -> None:
    """leak recovery 在 parse.response 节点内部完成;compose.action 拿到 clean intent。

    合并节点的关键 invariant —— leaked JSON 不污染 intent,也不影响 action_type 分支。
    """
    response = LLMResponse(
        text='我先看下文件。\n[Tool call: listFiles]\n{"path": "/tmp"}',
        finish_reason="tool_calls",
        tool_calls=[],
    )
    output = _run_graph(response)
    decision = output["decision"]
    assert decision.action_type == ActionType.USE_TOOL.value
    assert decision.tool_calls[0].tool_name == "listFiles"
