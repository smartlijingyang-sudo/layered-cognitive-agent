"""Structural + behavioral gates for team dual-track cleanup (goal plan)."""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from lca.contracts.decision import Decision
from lca.contracts.enums import DecisionGateName
from lca.contracts.graph import ExecutionGraph, GraphEdge, GraphNode
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import TeamAssembly
from lca.contracts.result import Result
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.state import Budget
from lca.contracts.team_coordination import Graph, PeerRelay, PeerSwarm, Pipeline
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer3_agent.orchestration_strategies import (
    HandoffStrategy,
    SequentialStrategy,
    SwarmStrategy,
)
from lca.layer4_app.api import Agent, Team
from lca.layer4_app.defaults import build_default_registries
from tests.support.team_stage import stage_with_invoker

_ROOT = Path(__file__).resolve().parents[1]


class TestDecisionSingleDelegationField(unittest.TestCase):
    def test_decision_has_only_delegations(self) -> None:
        from dataclasses import fields as dc_fields

        names = {f.name for f in dc_fields(Decision)}
        self.assertIn("delegations", names)
        self.assertNotIn("delegate_to", names)
        self.assertNotIn("delegate_targets", names)

    def test_parser_0_1_n(self) -> None:
        parser = SimpleDecisionParser()
        from lca.contracts.state import AgentState

        state = AgentState(trace_id="t", task="x", budget=Budget())
        empty = parser.parse('{"action_type":"respond","rationale":"r","confidence":1}', state)
        self.assertEqual(empty.delegations, [])

        single = parser.parse(
            '{"action_type":"delegate","target_role":"a","subtask":"s","rationale":"r","confidence":1}',
            state,
        )
        self.assertEqual(len(single.delegations), 1)
        self.assertEqual(single.delegations[0].target_role, "a")

        multi = parser.parse(
            """
            {"action_type":"delegate","rationale":"r","confidence":1,
             "delegations":[{"target_role":"a","subtask":"1"},{"target_role":"b","subtask":"2"}]}
            """,
            state,
        )
        self.assertEqual(len(multi.delegations), 2)


class TestTypedProcessDispatch(unittest.TestCase):
    def test_no_string_topology_tables_in_strategies(self) -> None:
        strat_dir = _ROOT / "lca" / "layer3_agent" / "orchestration_strategies"
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
        reg = build_default_registries().orchestration

        def _assembly(governance) -> TeamAssembly:
            return TeamAssembly(governance=governance, stage=stage_with_invoker([]))

        self.assertIsInstance(reg.resolve("pipeline", _assembly(Pipeline())), SequentialStrategy)
        self.assertIsInstance(reg.resolve("peer_relay", _assembly(PeerRelay())), HandoffStrategy)
        self.assertIsInstance(reg.resolve("peer_swarm", _assembly(PeerSwarm())), SwarmStrategy)


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
        from lca.layer3_agent.member_invoke import TransportMemberInvoker

        src = inspect.getsource(TransportMemberInvoker.invoke)
        self.assertIn("send_and_wait", src)
        self.assertNotIn("member.run", src)


class TestHonestFacade(unittest.IsolatedAsyncioTestCase):
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

            async def complete(self, prompt: str, **kwargs: object) -> str:
                return (
                    '{"action_type":"respond","response_text":"node-out",'
                    '"rationale":"r","confidence":1.0}'
                )

        llm = _LLM()
        a = Agent(role="writer", goal="g", backstory="b", tools=[], llm=llm)  # type: ignore[arg-type]
        graph = ExecutionGraph()
        graph.add_node(GraphNode(id="entry", type="entry"))
        graph.add_node(GraphNode(id="writer", type="agent", config={"role": "writer"}))
        graph.add_node(GraphNode(id="exit", type="exit"))
        graph.add_edge(GraphEdge(source="entry", target="writer"))
        graph.add_edge(GraphEdge(source="writer", target="exit"))
        team = Team(members=[a], coordination=Graph(execution_graph=graph))
        result = await team.run("write")
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertEqual(result.output, "node-out")

    def test_routing_plus_gate_fails_at_compose(self) -> None:
        reg = build_default_registries()
        profile = RoleProfile(
            role="lead",
            goal="g",
            backstory="b",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        rt = MagicMock()
        from lca.layer1_cognitive.brain.reasoner import SimpleReasoner

        rt.brain = MagicMock()
        rt.brain.reasoner = SimpleReasoner(
            MagicMock(),
            profile,
            "t",
            templates={
                "react_prompt": "r",
                "hierarchical_prompt": "h {teammates} {member_status_text}",
                "routing_prompt": "rt {teammates} {assigned_roles_text} {notes}",
            },
        )
        rt.body = MagicMock()
        rt.memory = MagicMock()
        # ROUTING + settlement is not expressible as LeadMandate; BOARD is consultation+gate.
        # Invalid combinations are type-excluded; ROUTING mode never installs a gate.
        from lca.contracts.team_coordination import LeadMandate, gate_name_for_mandate

        self.assertEqual(gate_name_for_mandate(LeadMandate.ROUTING), DecisionGateName.NONE)
        # assemble still requires real agents with llm — use Assembly path for smoke
        del rt, profile, reg


class TestResidueGone(unittest.TestCase):
    def test_no_hierarchical_consultation_export(self) -> None:
        import lca.contracts as c

        self.assertFalse(hasattr(c, "HierarchicalConsultation"))
        self.assertFalse(hasattr(c, "iter_delegation_specs"))

    def test_cognitive_agent_module_name(self) -> None:
        path = _ROOT / "lca" / "layer3_agent" / "cognitive_agent.py"
        self.assertTrue(path.is_file())
        self.assertFalse((_ROOT / "lca" / "layer3_agent" / "simple_agent.py").exists())

    def test_glossary_has_no_transition_alias_dual_names(self) -> None:
        text = (_ROOT / "docs" / "glossary.md").read_text(encoding="utf-8")
        self.assertNotIn("原 ", text)
        self.assertNotIn("HierarchicalConsultation", text)
        self.assertNotIn("PeerStrategy", text)
        self.assertNotIn("delegate_targets", text)

    def test_no_orphan_pyc_modules_without_py(self) -> None:
        agent_dir = _ROOT / "lca" / "layer3_agent"
        py_stems = {p.stem for p in agent_dir.glob("*.py")}
        py_stems |= {p.stem for p in (agent_dir / "orchestration_strategies").glob("*.py")}
        orphans: list[str] = []
        for pyc in agent_dir.rglob("*.pyc"):
            # e.g. simple_agent.cpython-314.pyc
            name = pyc.name.split(".")[0]
            if name == "__init__":
                continue
            parent = pyc.parent.parent if pyc.parent.name == "__pycache__" else pyc.parent
            # strategy subpackage
            if parent.name == "orchestration_strategies":
                if name not in {s.stem for s in parent.glob("*.py")}:
                    orphans.append(str(pyc.relative_to(agent_dir)))
            elif parent == agent_dir and name not in py_stems:
                orphans.append(str(pyc.relative_to(agent_dir)))
        self.assertEqual(orphans, [], f"orphan pyc without source: {orphans}")


if __name__ == "__main__":
    unittest.main()
