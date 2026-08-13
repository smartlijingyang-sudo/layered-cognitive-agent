"""Gateway team 组队执行路径测试（ADR-0052）：mode=team 经 run_executor 全链路。"""

from __future__ import annotations

import json
import unittest

from gateway.run_executor import create_run_session, execute_run, set_llm_resolver
from gateway.run_registry import RunRegistry, RunStatus
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.protocols import LLMAdapter
from lca.layer0_infra.llm_resolver import ProductionLLMResolver
from tests.harness.scripted_llm import ScriptedLLMAdapter


class _ScriptedResolver:
    """测试替身：直接返回注入的脚本化 LLM。"""

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm

    def is_available(self) -> bool:
        return True

    def resolve(self, *, mode: str) -> LLMAdapter:
        del mode
        return self._llm


def _journal_event_types(session: RunStatus) -> set[str]:
    """Read event types from the EventStream buffer (replaces old hub.journal access)."""
    from gateway.run_registry import RunSession

    assert isinstance(session, RunSession)
    return {type(stamped.event).__name__ for stamped in session.stream.buffered_after()}


class TestTeamRunPath(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.registry = RunRegistry()

    def tearDown(self) -> None:
        set_llm_resolver(ProductionLLMResolver())

    async def test_team_mode_casts_team_and_completes(self) -> None:
        plan = json.dumps(
            {
                "selected": [
                    {"role_id": "product/product-manager"},
                    {"role_id": "marketing/marketing-content-creator"},
                ],
                "governance": {"kind": "pipeline"},
                "rationale": "先需求后文案",
            },
            ensure_ascii=False,
        )
        llm = ScriptedLLMAdapter(
            {"caster": [LLMResponse(text=plan, model="scripted-llm")]}, default_respond=True
        )
        set_llm_resolver(_ScriptedResolver(llm))

        session = create_run_session(
            self.registry,
            question="给新功能的发布写一句宣传文案",
            user_text="给新功能的发布写一句宣传文案",
            mode="team",
        )
        await execute_run(
            self.registry,
            run_id=session.run_id,
            question=session.question,
            mode=session.mode,
        )
        self.assertEqual(session.status, RunStatus.COMPLETED)
        event_types = {type(stamped.event).__name__ for stamped in session.stream.buffered_after()}
        self.assertIn("CastingStarted", event_types)
        self.assertIn("CastingCompleted", event_types)

    async def test_team_mode_casting_failure_fails_run(self) -> None:
        # 两次尝试都不是合法 JSON → CastingError → run FAILED（既有错误管道收尾）
        llm = ScriptedLLMAdapter(
            {"caster": [LLMResponse(text="完全不是 JSON", model="scripted-llm")]},
            default_respond=False,
        )
        set_llm_resolver(_ScriptedResolver(llm))

        session = create_run_session(
            self.registry,
            question="随便做点什么",
            user_text="随便做点什么",
            mode="team",
        )
        await execute_run(
            self.registry,
            run_id=session.run_id,
            question=session.question,
            mode=session.mode,
        )
        self.assertEqual(session.status, RunStatus.FAILED)
        assert session.error is not None
        self.assertIn("自动组队失败", session.error)
        event_types = {type(stamped.event).__name__ for stamped in session.stream.buffered_after()}
        self.assertIn("CastingStarted", event_types)
        self.assertIn("CastingFailed", event_types)


if __name__ == "__main__":
    unittest.main()
