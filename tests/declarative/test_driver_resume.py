"""Tests for the declarative checkpoint recovery seam."""

from unittest.mock import AsyncMock

import pytest

from lca.contracts.models.core.state import AgentState, Budget, StateSnapshot
from lca.contracts.protocols.declarative_phase_graph import (
    DeclarativeValidationError,
    PhaseRunCursor,
)
from lca.layer2_runtime.checkpoint_resolution import (
    DeclarativeCheckpoint,
    DeclarativeCheckpointStateResolver,
)
from lca.layer2_runtime.declarative_runtime import DeclarativeRuntimeDriver

EXPECTED_PLAN_REF = "expected-plan-ref"


def _cursor(plan_ref: str = EXPECTED_PLAN_REF) -> PhaseRunCursor:
    return PhaseRunCursor(
        plan_ref=plan_ref,
        node_id="think.resume",
        visit_counts=(),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={},
    )


def _state() -> AgentState:
    return AgentState(trace_id="trace-resume", task="resume", budget=Budget())


def _checkpoint(
    *,
    plan_ref: str = EXPECTED_PLAN_REF,
    resume_state: AgentState | None = None,
) -> DeclarativeCheckpoint:
    return DeclarativeCheckpoint(
        state_snapshot=StateSnapshot(
            snapshot_id="snapshot-resume",
            step=3,
            state_ref="state://checkpoint-resume",
        ),
        cursor=_cursor(plan_ref),
        plan_ref=plan_ref,
        resume_state=resume_state,
    )


def test_declarative_runtime_driver_has_resume() -> None:
    """The carrier adapter retains the stable public resume entry point."""

    assert callable(DeclarativeRuntimeDriver.resume)


@pytest.mark.asyncio
async def test_checkpoint_resolver_rejects_a_checkpoint_for_another_plan() -> None:
    """A checkpoint must never resume under a different compiled plan."""

    resolver = DeclarativeCheckpointStateResolver(state_store=None)

    with pytest.raises(DeclarativeValidationError, match="plan_ref mismatch"):
        await resolver.resolve(
            _checkpoint(plan_ref="another-plan-ref"), expected_plan_ref=EXPECTED_PLAN_REF
        )


@pytest.mark.asyncio
async def test_checkpoint_resolver_uses_post_resume_state_without_loading_store() -> None:
    """A caller-provided post-resume state avoids a redundant persistence read."""

    state = _state()
    state_store = AsyncMock()
    resolver = DeclarativeCheckpointStateResolver(state_store=state_store)

    resolved = await resolver.resolve(
        _checkpoint(resume_state=state), expected_plan_ref=EXPECTED_PLAN_REF
    )

    assert resolved is state
    state_store.load.assert_not_awaited()


@pytest.mark.asyncio
async def test_checkpoint_resolver_loads_durable_state_when_memory_state_is_absent() -> None:
    """A durable checkpoint reloads its state through the StateStore seam."""

    state = _state()
    state_store = AsyncMock()
    state_store.load.return_value = state
    resolver = DeclarativeCheckpointStateResolver(state_store=state_store)

    resolved = await resolver.resolve(_checkpoint(), expected_plan_ref=EXPECTED_PLAN_REF)

    assert resolved is state
    state_store.load.assert_awaited_once_with("state://checkpoint-resume")


@pytest.mark.asyncio
async def test_checkpoint_resolver_fails_closed_without_any_state_source() -> None:
    """A checkpoint without in-memory state requires an explicit StateStore."""

    resolver = DeclarativeCheckpointStateResolver(state_store=None)

    with pytest.raises(DeclarativeValidationError, match="requires a StateStore"):
        await resolver.resolve(_checkpoint(), expected_plan_ref=EXPECTED_PLAN_REF)


@pytest.mark.asyncio
async def test_checkpoint_resolver_updates_only_a_legacy_state_cursor_attribute() -> None:
    """Legacy state compatibility stays inside the recovery seam."""

    state = _state()
    state.phase_cursor = _cursor("legacy-plan-ref")  # type: ignore[attr-defined]
    checkpoint = _checkpoint(resume_state=state)
    resolver = DeclarativeCheckpointStateResolver(state_store=None)

    resolved = await resolver.resolve(checkpoint, expected_plan_ref=EXPECTED_PLAN_REF)

    assert resolved.phase_cursor is checkpoint.cursor  # type: ignore[attr-defined]


def test_checkpoint_rejects_cursor_for_another_plan() -> None:
    with pytest.raises(ValueError, match="cursor and plan_ref"):
        DeclarativeCheckpoint(
            state_snapshot=StateSnapshot(
                snapshot_id="snapshot-resume",
                step=3,
                state_ref="state://checkpoint-resume",
            ),
            cursor=_cursor("another-plan-ref"),
            plan_ref=EXPECTED_PLAN_REF,
        )


def test_checkpoint_requires_a_plan_reference() -> None:
    with pytest.raises(ValueError, match="plan_ref"):
        DeclarativeCheckpoint(
            state_snapshot=StateSnapshot(
                snapshot_id="snapshot-resume",
                step=3,
                state_ref="state://checkpoint-resume",
            ),
            cursor=_cursor(""),
            plan_ref="",
        )
