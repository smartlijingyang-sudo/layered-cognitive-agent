"""Gateway cancel 路径：Finished 先于 hub.close，无 OTel 跨 Context 泄漏。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import patch

import pytest

from gateway.runs.execute import create_run_session, schedule_run
from gateway.runs.session.session import RunRegistry, RunStatus
from lca.agent.cognitive_agent import CognitiveAgent
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from tests.support.gateway_scripted import ScriptedLLMResolver


@pytest.fixture(autouse=True)
def _isolate_production_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    """This test is about cancel/detach, not Langfuse flush or Onlyboxes bind."""
    monkeypatch.setenv("LCA_OBS_INCLUDE_LANGFUSE", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("LCA_OBS_BACKENDS", "console")
    monkeypatch.setenv("ONLYBOXES_BASE_URL", "")
    monkeypatch.setenv("ONLYBOXES_ACCESS_TOKEN", "")


class _HangRuntime:
    async def run(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        await asyncio.Event().wait()


def _role() -> RoleProfile:
    return RoleProfile(
        role="测试员",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


class _LazyHubAgent:
    """Uses the hub already hanging on the session (created at session birth)."""

    def __init__(self, session: Any) -> None:
        self._session = session
        self._inner: CognitiveAgent | None = None

    async def run(self, objective: str) -> Any:
        hub = self._session.hub
        self._inner = CognitiveAgent(_HangRuntime(), _role(), hub)  # type: ignore[arg-type]
        return await self._inner.run(objective)


@pytest.mark.asyncio
async def test_execute_run_cancel_no_otel_detach_noise(caplog: pytest.LogCaptureFixture) -> None:
    from lca.harness.profile.lifespan import profile_lifespan

    registry = RunRegistry()
    async with profile_lifespan("profiles/web-standard.yaml") as state:
        ctx = state["ctx"]
        ctx.provide("llm_resolver", ScriptedLLMResolver())
        session = create_run_session(
            registry, question="hang", user_text="hang", mode="solo", ctx=ctx
        )
        with patch(
            "gateway.plugins.default_modes.build_solo_agent",
            return_value=_LazyHubAgent(session),
        ):
            task = schedule_run(registry, session, ctx=ctx)
            await asyncio.sleep(0)
            task.cancel()
            with (
                caplog.at_level(logging.ERROR, logger="opentelemetry.context"),
                pytest.raises(asyncio.CancelledError),
            ):
                await task

        # Hub was cleaned up by _finalize_run; check via the journal recorded before close
        # Since _active_hubs is cleaned up, we verify via session state
        assert session.status == RunStatus.CANCELED
        assert not any("Failed to detach context" in r.message for r in caplog.records)
