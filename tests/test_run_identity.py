"""AgentRef is the isolation key. Two principals never share a Run."""

from __future__ import annotations

import unittest

from gateway.runs.identity import default_agent_ref, parse_agent_ref
from gateway.runs.session import RunRegistry, RunSession, RunStatus, run_dedup_key
from lca.contracts.atoms.ids import RunId, TraceId
from lca.contracts.models.observability.journal import RunScope
from lca.layer0_infra.observability.journal.live_tail import LiveTail
from lca.layer0_infra.observability.run_context import (
    TEAM_CONTAINER_ROLE,
    adopt_run_scope,
    run_scope,
)


class TestParseAgentRef(unittest.TestCase):
    def test_missing_is_default_solo(self) -> None:
        ref = parse_agent_ref(None)
        self.assertEqual(ref.agent_id, "solo")
        self.assertEqual(ref.name, "助手")

    def test_id_and_name(self) -> None:
        ref = parse_agent_ref({"id": "agt_helper", "name": "小助手"})
        self.assertEqual(ref.agent_id, "agt_helper")
        self.assertEqual(ref.name, "小助手")

    def test_id_only_does_not_collapse_to_default_name(self) -> None:
        ref = parse_agent_ref({"id": "agt_helper"})
        self.assertEqual(ref.agent_id, "agt_helper")
        self.assertEqual(ref.name, "agt_helper")


class TestAgentIsolation(unittest.TestCase):
    def test_same_text_different_agent_is_different_key(self) -> None:
        a = run_dedup_key(user_text="分析这个文件", mode="solo", agent_id="solo")
        b = run_dedup_key(user_text="分析这个文件", mode="solo", agent_id="agt_helper")
        self.assertNotEqual(a, b)

    def test_inflight_does_not_cross_agents(self) -> None:
        registry = RunRegistry()
        session = RunSession(
            run_id="run_main",
            trace_id="t",
            jsonl_path=registry.jsonl_path_for("run_main"),
            tail=LiveTail(),
            question="分析这个文件",
            user_text="分析这个文件",
            mode="solo",
            agent=parse_agent_ref({"id": "solo", "name": "助手"}),
            status=RunStatus.RUNNING,
        )
        registry.put(session)
        self.assertIs(
            registry.find_inflight_run(user_text="分析这个文件", mode="solo", agent_id="solo"),
            session,
        )
        self.assertIsNone(
            registry.find_inflight_run(user_text="分析这个文件", mode="solo", agent_id="agt_helper")
        )


class TestDefaultAgentRef(unittest.TestCase):
    def test_default_matches_parse_empty(self) -> None:
        self.assertEqual(default_agent_ref(), parse_agent_ref({}))


class TestAdoptRunScope(unittest.TestCase):
    def test_claims_allocated_root(self) -> None:
        allocated = RunScope(trace_id=TraceId("trace_http"), run_id=RunId("run_http"))
        with run_scope(allocated):
            scope, is_root = adopt_run_scope(role="助手")
        self.assertTrue(is_root)
        self.assertEqual(scope.run_id, "run_http")
        self.assertEqual(scope.trace_id, "trace_http")
        self.assertEqual(scope.agent_role, "助手")

    def test_nested_actor_mints_child(self) -> None:
        claimed = RunScope(
            trace_id=TraceId("t"),
            run_id=RunId("run_http"),
            agent_role=TEAM_CONTAINER_ROLE,
        )
        with run_scope(claimed):
            scope, is_root = adopt_run_scope(role="研究员")
        self.assertFalse(is_root)
        self.assertNotEqual(scope.run_id, "run_http")
        self.assertEqual(scope.parent_run_id, "run_http")
        self.assertEqual(scope.agent_role, "研究员")

    def test_no_ambient_mints_root(self) -> None:
        scope, is_root = adopt_run_scope(role="助手")
        self.assertTrue(is_root)
        self.assertTrue(scope.run_id)
        self.assertEqual(scope.agent_role, "助手")
        self.assertIsNone(scope.parent_run_id)

    def test_resume_scope_reuses_trace_and_links_source_run(self) -> None:
        scope, is_root = adopt_run_scope(
            role="助手",
            trace_id=TraceId("trace-paused"),
            parent_run_id=RunId("run-paused"),
        )

        self.assertFalse(is_root)
        self.assertEqual(scope.trace_id, "trace-paused")
        self.assertNotEqual(scope.run_id, "run-paused")
        self.assertEqual(scope.parent_run_id, "run-paused")
