"""Gateway team 组队执行路径测试（ADR-0052）：mode=team 经 run_executor 全链路。"""

from __future__ import annotations

import json
import unittest

from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.protocols import LLMAdapter
from lca.plugins.transport.webserver.handlers.runs.execute import create_run_session, execute_run
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry, RunStatus
from lca_kernel import run_kernel_lifespan as profile_lifespan
from tests.harness.scripted_llm import ScriptedLLMAdapter


class _ScriptedResolver:
    """测试替身：直接返回注入的脚本化 LLM。"""

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm

    def is_available(self) -> bool:
        return True

    def resolve(self, *, mode: str | None = None) -> LLMAdapter:
        del mode
        return self._llm


def _journal_event_types(session: object) -> set[str]:
    from typing import cast

    from lca.infrastructure.observability.journal.engine.engine import RunStore
    from lca.infrastructure.observability.journal.engine.journal_io import read_journal
    from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession

    assert isinstance(session, RunSession)
    if session.hub is not None and session.hub.journal is not None:
        store = cast("RunStore", getattr(session.hub.journal, "store", session.hub.journal))
        return {type(stamped.event).__name__ for stamped in store.events}
    return {type(stamped.event).__name__ for stamped in read_journal(session.spine_path)}


class TestTeamRunPath(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.registry = RunRegistry()

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

        async with profile_lifespan("profiles/web-standard.yaml") as state:
            ctx = state["ctx"]
            ctx.provide("llm_resolver", _ScriptedResolver(llm))
            session = create_run_session(
                self.registry,
                question="给新功能的发布写一句宣传文案",
                user_text="给新功能的发布写一句宣传文案",
                mode="team",
                ctx=ctx,
            )
            await execute_run(
                self.registry,
                run_id=session.run_id,
                question=session.question,
                mode=session.mode,
                ctx=ctx,
            )
        self.assertEqual(session.status, RunStatus.COMPLETED)
        event_types = _journal_event_types(session)
        self.assertIn("CastingStarted", event_types)
        self.assertIn("CastingCompleted", event_types)

    async def test_solo_hello_does_not_fail_on_running_event_loop(self) -> None:
        """Gateway execute 跑在 uvicorn 已运行的 loop 上。

        Agent 无 scope 时曾用 loop.run_until_complete(boot_profile)，
        触发 RuntimeError: This event loop is already running。
        """
        llm = ScriptedLLMAdapter({}, default_respond=True)

        async with profile_lifespan("profiles/web-standard.yaml") as state:
            ctx = state["ctx"]
            ctx.provide("llm_resolver", _ScriptedResolver(llm))
            session = create_run_session(
                self.registry,
                question="你好",
                user_text="你好",
                mode="solo",
                ctx=ctx,
            )
            await execute_run(
                self.registry,
                run_id=session.run_id,
                question=session.question,
                mode=session.mode,
                ctx=ctx,
            )
        self.assertNotIn(
            "already running",
            (session.error or "").lower(),
            msg=session.error,
        )
        self.assertEqual(session.status, RunStatus.COMPLETED)
        event_types = _journal_event_types(session)
        self.assertIn("AgentRunStarted", event_types)
        assert session.hub is not None and session.hub.journal is not None
        from typing import cast

        from lca.infrastructure.observability.journal.engine.engine import RunStore

        store = cast("RunStore", getattr(session.hub.journal, "store", session.hub.journal))
        started = next(
            stamped for stamped in store.events if type(stamped.event).__name__ == "AgentRunStarted"
        )
        self.assertEqual(started.scope.run_id, session.run_id)

    async def test_team_mode_casting_failure_fails_run(self) -> None:
        # 两次尝试都不是合法 JSON → CastingError → run FAILED（既有错误管道收尾）
        llm = ScriptedLLMAdapter(
            {"caster": [LLMResponse(text="完全不是 JSON", model="scripted-llm")]},
            default_respond=False,
        )

        async with profile_lifespan("profiles/web-standard.yaml") as state:
            ctx = state["ctx"]
            ctx.provide("llm_resolver", _ScriptedResolver(llm))
            session = create_run_session(
                self.registry,
                question="随便做点什么",
                user_text="随便做点什么",
                mode="team",
                ctx=ctx,
            )
            await execute_run(
                self.registry,
                run_id=session.run_id,
                question=session.question,
                mode=session.mode,
                ctx=ctx,
            )
        self.assertEqual(session.status, RunStatus.FAILED)
        assert session.error is not None
        self.assertIn("自动组队失败", session.error)
        event_types = _journal_event_types(session)
        self.assertIn("CastingStarted", event_types)
        self.assertIn("CastingFailed", event_types)


if __name__ == "__main__":
    unittest.main()
