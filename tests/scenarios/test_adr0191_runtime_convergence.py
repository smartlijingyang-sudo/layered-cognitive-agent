"""ADR-0191 end-to-end convergence scenario tests."""

from __future__ import annotations

import pytest

from lca.contracts.harness.collaboration.agent import LiveAgentStatus
from lca.contracts.protocols.session.persistence_service import CheckpointFailure
from lca.infrastructure.session.bindings import (
    assemble_model_history,
    await_model_request_checkpoint,
)
from lca.infrastructure.session.model_context_assembler import default_model_context_assembler
from lca.infrastructure.session.surface_emit import append_human_answer_surface
from lca.session.lifecycle.recovery import recover_live_agent
from lca.session.lifecycle.repair import repair_interrupted_turn
from lca.session.append import Session
from lca_kernel.events.fold import SURFACE_ASSISTANT_TYPE, SURFACE_USER_TYPE


@pytest.mark.asyncio
async def test_model_context_parity_with_surface_events() -> None:
    session = Session("adr0191_1")
    session.append(
        SURFACE_USER_TYPE,
        {"content": "hi", "messages": [{"role": "user", "content": "hi"}]},
        surface_op="append",
    )
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "hello"}},
        surface_op="append",
    )
    assembled = default_model_context_assembler().assemble(session, step=1)
    assert assembled.messages == session.derive_messages()
    assert assemble_model_history(step=1) == []  # unbound


@pytest.mark.asyncio
async def test_checkpoint_fail_closed_blocks_llm_dispatch() -> None:
    from lca.plugins.events.publishers._session_publish import (
        reset_publish_session,
        set_publish_session,
    )

    session = Session("adr0191_2")

    class _AlwaysFailListener:
        async def flush(self, _session: object) -> None:
            raise OSError("disk full")

    session.register_flush_listener(_AlwaysFailListener())
    token = set_publish_session(session)
    try:
        with pytest.raises(CheckpointFailure, match="disk full"):
            await await_model_request_checkpoint()
    finally:
        reset_publish_session(token)


def test_repair_then_recover_idle() -> None:
    session = Session("adr0191_3")
    session.append("turn.started.v1", {"turn": 1})
    raw = list(session.snapshot_events())
    repaired = list(raw) + repair_interrupted_turn(raw)
    view = recover_live_agent(repaired)
    assert view.status is LiveAgentStatus.IDLE


def test_human_answer_surface_in_derive_messages() -> None:
    session = Session("adr0191_4")
    append_human_answer_surface(session, "user answer")
    messages = session.derive_messages()
    assert messages and messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "user answer"


def test_fold_deriver_prefers_session_snapshot(tmp_path) -> None:
    from lca.plugins.session.derivers.step_tree.fold_deriver import StepTreeFoldDeriver

    session = Session("adr0191_5")
    session.append("turn.started.v1", {"turn": 1})
    spine_path = tmp_path / "adr0191_5.spine.jsonl"
    spine_path.write_text('{"type":"orphan","seq":99,"time":1,"data":{}}\n', encoding="utf-8")
    deriver = StepTreeFoldDeriver(
        run_id="adr0191_5",
        run_dir=tmp_path,
        session=session,
        spine_path=spine_path,
    )
    events = list(deriver._iter_events())
    assert len(events) == 1
    assert events[0].type == "turn.started.v1"


@pytest.mark.asyncio
async def test_step_boundary_checkpoint_called_before_driver(monkeypatch) -> None:
    from lca.runtime.runtime_loop import CognitiveRuntime

    calls: list[str] = []

    async def _fake_checkpoint() -> None:
        calls.append("step_boundary")

    monkeypatch.setattr(
        "lca.infrastructure.session.bindings.await_step_boundary_checkpoint",
        _fake_checkpoint,
    )
    monkeypatch.setattr(
        "lca.infrastructure.session.runtime_emit.emit_lifecycle_finally",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "lca.infrastructure.session.runtime_emit.emit_exception_finally",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "lca.infrastructure.observability.spine.exception_emit.emit_exception_caught",
        lambda *_args, **_kwargs: None,
    )

    class _Hooks:
        async def trigger(self, *args, **kwargs) -> None:
            return None

    class _StubBindings:
        hooks = _Hooks()

        def require_executable_plan(self) -> None:
            return None

        def new_driver(self):
            class _Driver:
                async def run(self, state):
                    from lca.contracts.models.core.budget import create_budget
                    from lca.contracts.models.core.lifecycle import TaskStatus
                    from lca.contracts.models.core.result import Result

                    return Result(
                        trace_id="t",
                        status=TaskStatus.COMPLETED,
                        final_state_ref="state-ref",
                        total_steps=1,
                        budget_used=create_budget(max_steps=1),
                    )

            return _Driver()

        def new_state(self, **kwargs):
            return type("S", (), {"trace_id": "t", "phase_cursor": None, **kwargs})()

        def plan_ref(self) -> str:
            return "plan"

    class _Lifecycle:
        async def publish(self, *args, **kwargs) -> None:
            return None

        async def publish_terminal(self, state, result) -> None:
            return None

    runtime = CognitiveRuntime(_StubBindings())  # type: ignore[arg-type]
    runtime._lifecycle = _Lifecycle()  # type: ignore[assignment]
    await runtime.run("task")
    assert calls == ["step_boundary"]
