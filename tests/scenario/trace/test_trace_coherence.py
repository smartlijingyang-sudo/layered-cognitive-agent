"""Trace 连贯性不变量守卫 —— 「来龙去脉」是被测试强制的属性。

对一次真实（scripted）团队运行断言：
1. 单树性：唯一 run.team 根，所有 span 可回溯到根；
2. 资源 span 归属：llm.chat / tool.execute / memory.* 必在 run.agent 子树内；
   四相边界标记（pre/post）在每个 run.agent 子树内齐全；
3. 委派连续性：成员 run.agent 祖先链必含 delegation（ADR-0037 一等委派）；
4. 身份完备：相位/资源 span 必带 agent_role；
5. 内容完备：llm.chat 必带 model 与 prompt 预览。

.. note:: archaeology (2026-10-09, todo-93 / arch 09:09 裁决 (c)) ——
    本模块 premise 已被 ADR-0037 Stage 6（``4b9d4f135``）supersede：
    ambient OTel span 拓扑（run.agent / llm.chat / delegation / 无父
    transport.request-response）是刻意退役的机制平面调试细节；
    单树 / 委派连续性归属 journal→OtelProjector 投影面，
    不在 harness InMemory 采集路径内。5 个用例以 @unittest.skip
    考古标记保留证据链；test_phase_spans_carry_actor_identity 为真绿保留。
"""

from __future__ import annotations

# Scripted/mock run: boots the kernel, so it must pass the reasoner
# fail-loud credential gate (see tests/conftest.py _ensure_no_env).
# The mock/scripted adapter never touches the network; ambient dummy key is enough.
__keep_llm_key__ = True


import unittest

from lca.contracts.atoms.telemetry.telemetry import (
    ATTR_AGENT_ROLE,
    ATTR_MODEL,
    ATTR_PROMPT_PREVIEW,
    SpanName,
)
from tests.harness.collector import TraceBundle
from tests.harness.runner import run_team_scripted
from tests.harness.scripted_llm import ScriptedLLMAdapter, respond


def _ancestors(bundle: TraceBundle, span) -> list:
    by_id = {s.span_id: s for s in bundle.spans}
    out = []
    cur = span
    while cur.parent_span_id is not None and cur.parent_span_id in by_id:
        cur = by_id[cur.parent_span_id]
        out.append(cur)
    return out


def _has_ancestor_named(bundle: TraceBundle, span, *names: str) -> bool:
    return any(a.name in names for a in _ancestors(bundle, span))


class TestTraceCoherence(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from lca import Agent
        from lca.application.api.api import ensure_default_ctx
        from lca.contracts.models.team.team.coordination import Pipeline

        # Boot default plugin context for tests that need Agent construction
        scope = await ensure_default_ctx()

        llm = ScriptedLLMAdapter(
            {
                "研究员": [respond("研究结果")],
                "撰稿人": [respond("撰稿完成")],
            },
            default_respond=True,
        )
        members = [
            Agent(role="研究员", goal="研究", backstory="", tools=[], llm=llm, scope=scope),
            Agent(role="撰稿人", goal="撰稿", backstory="", tools=[], llm=llm, scope=scope),
        ]
        self.outcome = await run_team_scripted(
            members=members, coordination=Pipeline(), objective="写一份摘要"
        )
        self.bundle = self.outcome.bundle

    @unittest.skip(
        "archaeology: premise 已被 ADR-0037 Stage 6 (4b9d4f135) supersede——transport.request/response 为刻意无父的机制平面 span（verbose 调试细节），单树/委派连续性归属 journal→OtelProjector 投影面；本 harness 采集的是 ambient 平面，pin 读错了平面。"
    )
    def test_single_tree_no_orphans(self) -> None:
        roots = self.bundle.root_spans()
        self.assertEqual(len(roots), 1, f"应恰有一个根 span，实际 {[r.name for r in roots]}")
        root = roots[0]
        self.assertEqual(root.name, SpanName.RUN_TEAM.value)
        root_reachable = {s.span_id for s in self.bundle.walk(root)}
        all_ids = {s.span_id for s in self.bundle.spans}
        self.assertEqual(root_reachable, all_ids, "存在孤儿 span（不可回溯到根）")

    @unittest.skip(
        "archaeology: `run.agent` 在 lca/ + lca_kernel/ 内零真实发射点（ADR-0037 Stage 6，4b9d4f135 刻意退役）；迭代空集合即过，断言空心，算没测。"
    )
    def test_resource_spans_live_inside_agent_loops(self) -> None:
        """资源 span 必须归属于某个 run.agent 子树（认知循环上下文）。"""
        resource_names = (
            SpanName.LLM_CHAT.value,
            SpanName.TOOL_EXECUTE.value,
            SpanName.MEMORY_READ.value,
            SpanName.MEMORY_WRITE.value,
        )
        for name in resource_names:
            for s in self.bundle.by_name(name):
                self.assertTrue(
                    _has_ancestor_named(self.bundle, s, SpanName.RUN_AGENT.value),
                    f"{name} 不在任何 run.agent 子树内：{s.span_id}",
                )

    @unittest.skip(
        "archaeology: 迭代对象 run.agent 子树在 ADR-0037 Stage 6 (4b9d4f135) 后不存在，空集合即过，断言空心，算没测。"
    )
    def test_all_four_phase_markers_present_per_agent(self) -> None:
        """每个 run.agent 子树必含四相边界标记（相位完整性）。"""
        phase_names = {
            SpanName.LOOP_PHASE_PERCEIVE.value,
            SpanName.LOOP_PHASE_THINK.value,
            SpanName.LOOP_PHASE_ACT.value,
            SpanName.LOOP_PHASE_REFLECT.value,
        }
        for agent_root in self.bundle.by_name(SpanName.RUN_AGENT.value):
            subtree_names = {n.name for n in self.bundle.walk(agent_root)}
            missing = phase_names - subtree_names
            self.assertEqual(
                missing, set(), f"run.agent 子树缺少相位标记：{missing}（{agent_root.span_id}）"
            )

    @unittest.skip(
        "archaeology: `run.agent`/`SpanName.DELEGATION` 在 lca/ + lca_kernel/ 内零真实发射点（4b9d4f135 退役；委派连续性由 journal 投影承载，不在 harness 采集路径）；成员工作经 transport send_and_wait。"
    )
    def test_member_runs_chain_through_delegation(self) -> None:
        member_runs = [
            s
            for s in self.bundle.by_name(SpanName.RUN_AGENT.value)
            if s.attributes.get(ATTR_AGENT_ROLE) in ("研究员", "撰稿人")
        ]
        self.assertGreaterEqual(len(member_runs), 2)
        for s in member_runs:
            self.assertTrue(
                _has_ancestor_named(self.bundle, s, SpanName.DELEGATION.value),
                f"成员 run.agent 缺少 delegation 祖先（委派断链）：{s.span_id}",
            )

    def test_phase_spans_carry_actor_identity(self) -> None:
        for name in (
            SpanName.LOOP_PHASE_PERCEIVE.value,
            SpanName.LOOP_PHASE_THINK.value,
            SpanName.LOOP_PHASE_ACT.value,
            SpanName.LOOP_PHASE_REFLECT.value,
        ):
            for s in self.bundle.by_name(name):
                self.assertTrue(
                    s.attributes.get(ATTR_AGENT_ROLE),
                    f"{name} 缺少 agent_role（身份盖章失效）：{s.span_id}",
                )

    @unittest.skip(
        "archaeology: `llm.chat` 在 lca/ + lca_kernel/ 内零真实发射点（ADR-0037 Stage 6，4b9d4f135 刻意退役）；pin 所钉的 span 拓扑已不存在。"
    )
    def test_llm_chat_spans_carry_model_and_preview(self) -> None:
        chats = self.bundle.by_name(SpanName.LLM_CHAT.value)
        self.assertGreater(len(chats), 0)
        for s in chats:
            self.assertTrue(s.attributes.get(ATTR_MODEL), f"llm.chat 缺 model：{s.span_id}")
            self.assertTrue(
                s.attributes.get(ATTR_PROMPT_PREVIEW),
                f"llm.chat 缺 prompt 预览：{s.span_id}",
            )


if __name__ == "__main__":
    unittest.main()
