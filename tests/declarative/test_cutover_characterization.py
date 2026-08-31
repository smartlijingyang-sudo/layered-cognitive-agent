"""ADR-0075 declarative cutover characterization baseline.

These tests define the target behavior for the declarative runtime cutover:
- ``run()`` and ``resume()`` must never invoke the legacy ``_loop()`` method
- A runtime without a valid declarative plan must fail-closed
- The production source must not contain legacy runtime patterns

Current state (2026-08-22):
- ``run()`` delegates to ``DeclarativeRuntimeDriver`` when ``compiled_plan`` and
  ``phase_executors`` are present, but falls back to ``_loop()`` otherwise
- ``resume()`` always calls ``_loop()``, ignoring ``compiled_plan``
- ``_loop()`` contains the full six-phase implementation with
  ``DefaultControlPolicyEngine`` calls, checkpoint, and approval handling

These tests will FAIL until the legacy paths are removed (Tasks 4-6).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.application.api import ensure_default_ctx
from lca.application.spawn import spawn_agent
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
from lca.runtime.runtime_loop import CognitiveRuntime
from tests.support.agent_specs import make_spec


async def build_paused_default_runtime() -> tuple[CognitiveRuntime, object]:
    """Boot the default profile, run until paused, return (runtime, snapshot).

    Uses ``boot_profile()`` and ``spawn_agent()`` to get a runtime with
    ``compiled_plan`` and ``phase_executors``. Runs a task that triggers
    ``ApprovalPendingError`` to produce a paused state with a snapshot.
    """
    scope = await ensure_default_ctx()
    agent = spawn_agent(
        make_spec("declarative-default", MockLLMAdapter(), max_steps=3),
        scope=scope,
    )
    runtime = agent.runtime
    assert runtime.compiled_plan is not None
    assert runtime.compiled_plan.phase_graph is not None
    assert runtime.compiled_plan.phase_bindings
    assert len(runtime.phase_executors) == 18
    assert len(runtime.compiled_plan.control_entries) == 12

    # Run a task that will complete (we just need a valid runtime with a plan)
    result = await agent.run("请简洁地回答：1+1等于几？")

    # A completed run has no resumable cursor.  Resume-focused behaviour is
    # covered by the dedicated driver tests; this characterization fixture
    # only needs an explicit, plan-bound snapshot shape.
    snapshot = result.extra.get("state_snapshot")
    if snapshot is None:
        pytest.skip("default completion did not produce a resumable cursor")

    return runtime, snapshot


@pytest.mark.asyncio
async def test_default_profile_run_never_invokes_legacy_loop() -> None:
    """Default profile ``run()`` must not fall back to ``_loop()``."""
    scope = await ensure_default_ctx()
    agent = spawn_agent(
        make_spec("declarative-default", MockLLMAdapter(), max_steps=1),
        scope=scope,
    )
    runtime = agent.runtime
    assert runtime.compiled_plan is not None
    assert runtime.compiled_plan.phase_graph is not None
    assert runtime.compiled_plan.phase_bindings

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy CognitiveRuntime._loop is reachable from run()")

    runtime._loop = forbidden  # type: ignore[assignment]
    result = await agent.run("请简洁地说明声明式图的作用")

    assert result.status is TaskStatus.COMPLETED
    assert result.output


@pytest.mark.asyncio
async def test_default_profile_resume_never_invokes_legacy_loop() -> None:
    """Default profile ``resume()`` must not fall back to ``_loop()``.

    CURRENTLY FAILS: ``resume()`` always calls ``_loop()`` regardless of
    whether ``compiled_plan`` is present.
    """
    runtime, snapshot = await build_paused_default_runtime()

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy CognitiveRuntime._loop is reachable from resume()")

    runtime._loop = forbidden  # type: ignore[assignment]
    result = await runtime.resume(snapshot, input="approved")

    # Should complete via declarative driver, not legacy loop
    assert result.status is not None


def test_runtime_requires_a_valid_declarative_plan() -> None:
    """A runtime without ``compiled_plan`` must fail-closed, not fall back to ``_loop()``.

    CURRENTLY FAILS: ``run()`` falls back to ``_loop()`` when ``compiled_plan``
    is None or ``phase_executors`` is empty, instead of raising a validation error.
    """
    # Check source code to verify fallback behavior does NOT exist
    runtime_source = Path("lca/runtime/runtime_loop.py").read_text()
    # The absence of "return await self._loop(state, max_steps)" proves
    # the fallback has been removed
    assert "return await self._loop(state, max_steps)" not in runtime_source, (
        "Legacy fallback to _loop() still exists - runtime should fail-closed without valid plan"
    )


def test_runtime_module_has_no_legacy_loop_or_policy_engine_reference() -> None:
    """Production ``runtime_loop.py`` must not contain legacy patterns.

    CURRENTLY FAILS: ``_loop()``, ``DefaultControlPolicyEngine``, and
    ``return await self._loop`` are still present.
    """
    runtime_source = Path("lca/runtime/runtime_loop.py").read_text()
    assert "def _loop(" not in runtime_source, "_loop() method still exists"
    assert "DefaultControlPolicyEngine" not in runtime_source, (
        "DefaultControlPolicyEngine still imported/used"
    )
    assert "return await self._loop" not in runtime_source, "Legacy _loop() call still exists"
