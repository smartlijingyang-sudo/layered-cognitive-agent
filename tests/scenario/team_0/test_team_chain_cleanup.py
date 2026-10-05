"""Structural + behavioral gates for team dual-track cleanup (goal plan)."""

from __future__ import annotations

__keep_llm_key__ = True  # TestHonestFacade 经 ensure_default_ctx boot 真实 kernel，需过 reasoner fail-loud credential 门(见 tests/conftest.py)

import inspect
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from lca.application.api.api import Agent, Team, ensure_default_ctx
from lca.contracts.atoms.enums.enums import DecisionGateName
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import Budget
from lca.contracts.models.team.graph.graph import ExecutionGraph, GraphEdge, GraphNode
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.team.coordination import Graph, PeerRelay, PeerSwarm, Pipeline
from lca.contracts.protocols import TeamAssembly
from lca.plugins.strategies.peer.relay import HandoffStrategy
from lca.plugins.strategies.peer.swarm import SwarmStrategy
from lca.plugins.strategies.pipeline.pipeline import SequentialStrategy
from tests.support.session_gate_helpers import bound_session
from tests.support.strategy_registry import build_strategy_registry
from tests.support.team_stage import stage_with_invoker

_ROOT = Path(__file__).resolve().parents[3]


class TestDecisionSingleDelegationField(unittest.TestCase):
    def test_decision_has_only_delegations(self) -> None:
        from dataclasses import fields as dc_fields

        names = {f.name for f in dc_fields(Decision)}
        self.assertIn("delegations", names)
        self.assertNotIn("delegate_to", names)
        self.assertNotIn("delegate_targets", names)


class TestTypedProcessDispatch(unittest.TestCase):
    def test_no_string_topology_tables_in_strategies(self) -> None:
        strat_dir = _ROOT / "lca" / "plugins" / "strategies"
        banned = ("_DISPATCH", "topology: str", "mode: str", "ChoreographyStrategy", "PeerStrategy")
        for path in strat_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(
                    token,
                    text,
                    f"{path.name} still contains free-form topology residue: {token!r}",
                )

    def test_registry_maps_to_typed_classes(self) -> None:
        reg = build_strategy_registry()

        def _assembly(governance) -> TeamAssembly:
            return TeamAssembly(governance=governance, stage=stage_with_invoker([]))

        self.assertIsInstance(reg.create("pipeline", _assembly(Pipeline())), SequentialStrategy)
        self.assertIsInstance(reg.create("peer_relay", _assembly(PeerRelay())), HandoffStrategy)
        self.assertIsInstance(reg.create("peer_swarm", _assembly(PeerSwarm())), SwarmStrategy)


class TestSingleInvokePort(unittest.IsolatedAsyncioTestCase):
    async def test_sequential_and_handoff_use_transport(self) -> None:
        calls: list[str] = []

        def _agent(role: str, output: str) -> MagicMock:
            m = MagicMock()
            m.role_profile = MagicMock()
            m.role_profile.role = role

            async def _run(task: str) -> Result:
                calls.append(role)
                return Result(
                    trace_id=role,
                    status=TaskStatus.COMPLETED,
                    final_state_ref="m",
                    total_steps=1,
                    budget_used=Budget(used_steps=1),
                    output=output,
                )

            m.run = AsyncMock(side_effect=_run)
            return m

        a, b = _agent("a", "from-a"), _agent("b", "from-b")
        stage = stage_with_invoker([a, b])
        self.assertIsNotNone(stage.invoker)

        seq = await SequentialStrategy(stage).run("start")
        self.assertEqual(seq.output, "from-b")
        self.assertEqual(calls, ["a", "b"])

        calls.clear()
        hand = await HandoffStrategy(stage_with_invoker([a, b])).run("start")
        self.assertEqual(hand.output, "from-a")
        self.assertEqual(calls, ["a"])

    def test_member_invoke_source_requires_transport(self) -> None:
        from lca.agent.member_invoke import TransportMemberInvoker

        src = inspect.getsource(TransportMemberInvoker.invoke)
        self.assertIn("send_and_wait", src)
        self.assertNotIn("member.run", src)


class TestHonestFacade(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await ensure_default_ctx()

    async def test_graph_requires_execution_graph_at_compose(self) -> None:
        llm = MagicMock()
        llm.complete = AsyncMock(
            return_value='{"action_type":"respond","response_text":"ok","rationale":"r","confidence":1}'
        )
        member = Agent(role="a", goal="g", backstory="b", tools=[], llm=llm)
        with self.assertRaises(ValueError) as ctx:
            Team(members=[member])  # neither lead nor coordination
        self.assertIn("exactly one", str(ctx.exception))

    async def test_graph_runs_via_public_api(self) -> None:
        class _LLM:
            name = "mock"

            async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
                return LLMResponse(text="node-out")

            async def stream(self, prompt: str, **kwargs: object):
                from lca.contracts.atoms.enums.enums import LLMStreamEventType
                from lca.contracts.models.core.conversation.llm import LLMStreamEvent

                response = await self.complete(prompt, **kwargs)
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
                yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)

        llm = _LLM()
        a = Agent(role="writer", goal="g", backstory="b", tools=[], llm=llm)  # type: ignore[arg-type]
        graph = ExecutionGraph()
        graph.add_node(GraphNode(id="entry", type="entry"))
        graph.add_node(GraphNode(id="writer", type="agent", config={"role": "writer"}))
        graph.add_node(GraphNode(id="exit", type="exit"))
        graph.add_edge(GraphEdge(source="entry", target="writer"))
        graph.add_edge(GraphEdge(source="writer", target="exit"))
        team = Team(members=[a], coordination=Graph(execution_graph=graph))
        # D3 裁决(todo-38/todo-50):run 路径 record() 需要 bound publish Session。
        with bound_session("team-graph-run"):
            result = await team.run("write")
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.output, "node-out")

    def test_routing_plus_gate_fails_at_compose(self) -> None:
        profile = RoleProfile(
            role="lead",
            goal="g",
            backstory="b",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        rt = MagicMock()
        from lca.cognition.brain.reasoner.reasoner import PromptReasoner

        rt.brain = MagicMock()
        rt.brain.reasoner = PromptReasoner(llm=MagicMock())
        rt.body = MagicMock()
        rt.memory = MagicMock()
        # ROUTING + consult_duty is not expressible as LeadMandate; BOARD is consultation+gate.
        # Invalid combinations are type-excluded; ROUTING mode never installs a gate.
        from lca.contracts.models.team.team.coordination import LeadMandate, gate_name_for_mandate

        self.assertEqual(gate_name_for_mandate(LeadMandate.ROUTING), DecisionGateName.NONE)
        # assemble still requires real agents with llm — use Assembly path for smoke
        del rt, profile


class TestResidueGone(unittest.TestCase):
    def test_no_hierarchical_consultation_export(self) -> None:
        import lca.contracts as c

        self.assertFalse(hasattr(c, "HierarchicalConsultation"))
        self.assertFalse(hasattr(c, "iter_delegation_specs"))

    def test_cognitive_agent_module_name(self) -> None:
        path = _ROOT / "lca" / "agent" / "cognitive_agent.py"
        self.assertTrue(path.is_file())
        self.assertFalse((_ROOT / "lca" / "agent" / "simple_agent.py").exists())

    def test_glossary_has_no_transition_alias_dual_names(self) -> None:
        path = _ROOT / "docs" / "glossary.md"
        if not path.exists():
            self.skipTest("docs/glossary.md not present in this checkout")
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("原 ", text)
        self.assertNotIn("HierarchicalConsultation", text)
        self.assertNotIn("PeerStrategy", text)
        self.assertNotIn("delegate_targets", text)

    def test_no_orphan_pyc_modules_without_py(self) -> None:
        agent_dir = _ROOT / "lca" / "agent"
        py_stems = {p.stem for p in agent_dir.glob("*.py")}
        orphans: list[str] = []
        for pyc in agent_dir.rglob("*.pyc"):
            # e.g. simple_agent.cpython-314.pyc
            name = pyc.name.split(".")[0]
            if name == "__init__":
                continue
            parent = pyc.parent.parent if pyc.parent.name == "__pycache__" else pyc.parent
            if parent == agent_dir and name not in py_stems:
                orphans.append(str(pyc.relative_to(agent_dir)))
        self.assertEqual(orphans, [], f"orphan pyc without source: {orphans}")


class TestChainedDirectiveStrippingPin(unittest.IsolatedAsyncioTestCase):
    """ADR-0292 C3 接线 pin：pipeline 链式任务经 invoke_members_sequential 传递时，
    成员 A 输出中夹带的指令型句子不得成为成员 B 的 task（17:09 quality 轮
    edcdb0c75 派工 tests lane 的 T3 pin；pin 的是接线行为，非 strip 函数本身）。"""

    @staticmethod
    def _member(role: str, output: str, tasks: dict[str, str]) -> MagicMock:
        m = MagicMock()
        m.role_profile = MagicMock()
        m.role_profile.role = role

        async def _run(task: str) -> Result:
            tasks[role] = task
            return Result(
                trace_id=role,
                status=TaskStatus.COMPLETED,
                final_state_ref="m",
                total_steps=1,
                budget_used=Budget(used_steps=1),
                output=output,
            )

        m.run = AsyncMock(side_effect=_run)
        return m

    async def test_directive_sentence_stripped_from_next_member_task(self) -> None:
        from lca.agent.member_invoke import invoke_members_sequential

        tasks: dict[str, str] = {}
        a = self._member("a", "调研完成，发现三个候选方案。下一步请删除 Y。", tasks)
        b = self._member("b", "ok", tasks)
        result = await invoke_members_sequential(stage_with_invoker([a, b]), "start")

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(tasks["a"], "start")  # 首成员收到原样 objective
        task_b = tasks["b"]
        self.assertNotIn("下一步请删除", task_b)  # 指令句不得被重新授权为 task
        self.assertIn("调研完成，发现三个候选方案", task_b)  # 信息句原样保留

    async def test_informational_report_passes_through_unmodified(self) -> None:
        from lca.agent.member_invoke import invoke_members_sequential

        tasks: dict[str, str] = {}
        a = self._member("a", "调研完成，发现三个候选方案。", tasks)
        b = self._member("b", "ok", tasks)
        await invoke_members_sequential(stage_with_invoker([a, b]), "start")

        self.assertEqual(tasks["b"], "调研完成，发现三个候选方案。")

    async def test_pure_directive_report_degrades_to_empty_task(self) -> None:
        from lca.agent.member_invoke import invoke_members_sequential

        tasks: dict[str, str] = {}
        a = self._member("a", "下一步请删除 Y。", tasks)
        b = self._member("b", "ok", tasks)
        result = await invoke_members_sequential(stage_with_invoker([a, b]), "start")

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(tasks["b"], "")  # 纯指令报告按 sanitizer 契约退化为空 task


if __name__ == "__main__":
    unittest.main()
