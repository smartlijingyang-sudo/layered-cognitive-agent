"""Tests for PR-6 agent orchestration bindings."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from lca.contracts.protocols.agent.client import (
    AgentClient,
    AgentRequest,
    AgentResponse,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeInput
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.cognition.wire.agent_client_adapter import AgentClientAdapter
from lca.framework.graph import default_strategy_registry
from lca.framework.graph.strategies import (
    AgentConsultStrategy,
    AgentFanoutStrategy,
)


def _ctx(
    node_id: str = "x", *, target_agent: str | None = None, targets: tuple[str, ...] = ()
) -> StrategyContext:
    cfg: dict[str, Any] = {}
    if target_agent is not None:
        cfg["target_agent"] = target_agent
    if targets:
        cfg["targets"] = targets
    return StrategyContext(
        plan_ref="p",
        node_id=node_id,
        binding_kind=BindingKind.AGENT_CONSULT,
        node_config=cfg,
    )


class _RecordingClient(AgentClient):
    def __init__(self) -> None:
        self.calls: list[AgentRequest] = []

    async def consult(self, request: AgentRequest) -> AgentResponse:
        self.calls.append(request)
        return AgentResponse(
            source_agent=request.target_agent,
            status="ok",
            payload={"response": f"echo:{request.target_agent}"},
        )

    async def fanout(
        self, request: AgentRequest, *, targets: Sequence[str]
    ) -> Sequence[AgentResponse]:
        self.calls.append(request)
        return [
            AgentResponse(
                source_agent=t,
                status="ok",
                payload={"response": f"echo:{t}"},
            )
            for t in targets
        ]


class TestAgentConsultStrategy:
    async def test_consult_calls_client(self) -> None:
        client = _RecordingClient()
        strategy = AgentConsultStrategy(client=client)
        ctx = _ctx("n1", target_agent="planner")
        out = await strategy.execute(ctx, NodeInput(port_values={"decision": "d"}))
        assert out.port_values["response"] == "echo:planner"
        assert client.calls[0].target_agent == "planner"
        assert client.calls[0].payload == {"decision": "d"}

    async def test_failed_status_raises(self) -> None:
        class _FailClient(AgentClient):
            async def consult(self, request: AgentRequest) -> AgentResponse:
                return AgentResponse(
                    source_agent=request.target_agent,
                    status="failed",
                    error="kaboom",
                )

            async def fanout(
                self, request: AgentRequest, *, targets: Sequence[str]
            ) -> Sequence[AgentResponse]:
                return ()

        strategy = AgentConsultStrategy(client=_FailClient())
        with pytest.raises(RuntimeError, match="kaboom"):
            await strategy.execute(
                _ctx("n", target_agent="x"), NodeInput()
            )

    async def test_requires_target_agent(self) -> None:
        strategy = AgentConsultStrategy(client=_RecordingClient())
        with pytest.raises(RuntimeError, match="target_agent"):
            await strategy.execute(_ctx("n"), NodeInput())

    async def test_requires_client(self) -> None:
        strategy = AgentConsultStrategy()
        with pytest.raises(RuntimeError, match="without client"):
            await strategy.execute(
                _ctx("n", target_agent="x"), NodeInput()
            )


class TestAgentFanoutStrategy:
    async def test_fanout_runs_all_targets(self) -> None:
        client = _RecordingClient()
        strategy = AgentFanoutStrategy(client=client)
        ctx = _ctx("n1", targets=("a", "b", "c"))
        out = await strategy.execute(ctx, NodeInput(port_values={"decision": "d"}))
        # Last-write-wins reducer; final response is from "c".
        assert out.port_values["response"] == "echo:c"
        assert client.calls[0].target_agent == "*"

    async def test_requires_non_empty_targets(self) -> None:
        strategy = AgentFanoutStrategy(client=_RecordingClient())
        with pytest.raises(RuntimeError, match="non-empty"):
            await strategy.execute(_ctx("n"), NodeInput())

    async def test_requires_client(self) -> None:
        strategy = AgentFanoutStrategy()
        ctx = _ctx("n", targets=("a",))
        with pytest.raises(RuntimeError, match="without client"):
            await strategy.execute(ctx, NodeInput())


class TestRegistryAllBindings:
    def test_all_nine_kinds_registered(self) -> None:
        kinds = {k.value for k in default_strategy_registry().kinds()}
        expected = {
            "node_executor",
            "subgraph",
            "agent_consult",
            "agent_fanout",
            "gate_chain",
            "transform",
            "parallel",
            "observe",
            "terminate",
        }
        assert kinds == expected


class TestAgentClientAdapter:
    async def test_stub_consult(self) -> None:
        adapter = AgentClientAdapter()
        resp = await adapter.consult(
            AgentRequest(target_agent="planner", intent="plan")
        )
        assert resp.status == "ok"
        assert resp.source_agent == "planner"

    async def test_stub_fanout(self) -> None:
        adapter = AgentClientAdapter()
        responses = await adapter.fanout(
            AgentRequest(target_agent="*", intent="plan"),
            targets=("a", "b"),
        )
        assert [r.source_agent for r in responses] == ["a", "b"]

    async def test_executor_override(self) -> None:
        async def exec_fn(request: AgentRequest) -> dict:
            return {"decision": f"decided-by-{request.target_agent}"}

        adapter = AgentClientAdapter(executor=exec_fn)
        resp = await adapter.consult(
            AgentRequest(target_agent="planner", intent="plan")
        )
        assert resp.status == "ok"
        assert resp.payload == {"decision": "decided-by-planner"}

    async def test_executor_override_propagates_error(self) -> None:
        async def exec_fn(request: AgentRequest) -> None:
            return None

        adapter = AgentClientAdapter(executor=exec_fn)
        resp = await adapter.consult(
            AgentRequest(target_agent="planner", intent="plan")
        )
        assert resp.status == "failed"
        assert "empty response" in (resp.error or "")


class TestEndToEndAgentFixture:
    """Five-agent team fixture: planner, reasoner, critic, reflector, summarizer.

    Driver uses the new :class:`PlanInterpreter` + :class:`AgentClient`.
    Each agent responds with a deterministic stub; the kernel visits
    all five via the ``agent_consult`` strategy and the reducer
    fans in. This is the small E2E that proves the new kernel can
    drive a multi-agent plan.
    """

    async def test_five_agents_run_in_sequence(self) -> None:
        from lca.contracts.protocols.graph.node_io import PortSpec, NodeIOSchema
        from lca.contracts.protocols.graph.plan import Plan, PlanEdge, PlanNode
        from lca.framework.graph import PlanInterpreter, StrategyRegistry

        client = _RecordingClient()
        nodes = tuple(
            PlanNode(
                id=f"agent.{name}",
                binding=BindingKind.AGENT_CONSULT,
                io_schema=NodeIOSchema(
                    inputs=(PortSpec(name="decision"),),
                    outputs=(PortSpec(name="response"),),
                ),
                entry=(idx == 0),
                max_visits=1,
                config={"target_agent": name},
            )
            for idx, name in enumerate(
                ("planner", "reasoner", "critic", "reflector", "summarizer")
            )
        )
        edges = tuple(
            PlanEdge(source=nodes[i].id, target=nodes[i + 1].id)
            for i in range(len(nodes) - 1)
        )
        plan = Plan(id="team-fixture", nodes=nodes, edges=edges)
        registry = StrategyRegistry()
        registry.register(AgentConsultStrategy(client=client))
        interp = PlanInterpreter(registry=registry, artifacts={})
        result = await interp.run(plan)
        assert {v.node_id for v in result.visits} == {n.id for n in nodes}
        assert result.terminal_node == "agent.summarizer"
        # Each consult payload was forwarded through the port_values.
        assert any(v.outputs.get("response") == "echo:critic" for v in result.visits)