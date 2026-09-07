"""ADR-0191 runtime convergence invariants (skeleton).

Wave A–D 落地后逐步去 xfail。见 docs/adr/0191-runtime-loop-dsh-convergence-and-control-plane.md §10。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LCA_COGNITION = ROOT / "lca" / "cognition"
EXECUTOR = LCA_COGNITION / "brain" / "llm_turn" / "executor.py"
SAFE_EXECUTOR = LCA_COGNITION / "body" / "executor" / "safe_executor.py"


class TestModelContextRuntimePath:
    """I-MV-RUNTIME-2: cognition 生产路径不得依赖 build_tool_history。"""

    def test_executor_does_not_import_build_tool_history(self) -> None:
        src = EXECUTOR.read_text(encoding="utf-8")
        assert "build_tool_history" not in src


class TestCheckpointWiring:
    """I-CHK-1 / I-CHK-2: checkpoint policy awaited before LLM/tool dispatch."""

    def test_executor_awaits_checkpoint_before_llm(self) -> None:
        src = EXECUTOR.read_text(encoding="utf-8")
        assert (
            "before_model_request" in src
            or "SessionCheckpointPolicy" in src
            or "await_model_request_checkpoint" in src
        )

    def test_perceive_awaits_step_boundary_checkpoint(self) -> None:
        src = (
            ROOT / "lca/plugins/loop/phase/perceive/standard/plugin.py"
        ).read_text(encoding="utf-8")
        assert "await_step_boundary_checkpoint" in src

    def test_safe_executor_awaits_checkpoint_before_tool(self) -> None:
        src = SAFE_EXECUTOR.read_text(encoding="utf-8")
        assert (
            "before_tool_side_effect" in src
            or "SessionCheckpointPolicy" in src
            or "await_tool_side_effect_checkpoint" in src
        )


class TestSessionRepairModule:
    """I-RESUME-1: cold-load repair module exists."""

    def test_repair_module_exists(self) -> None:
        repair = ROOT / "lca" / "session" / "lifecycle" / "repair.py"
        assert repair.is_file()

    def test_recovery_module_exists(self) -> None:
        recovery = ROOT / "lca" / "session" / "lifecycle" / "recovery.py"
        assert recovery.is_file()


class TestControlPlaneProtocols:
    """I-CONTROL-1: control protocols exist; gates do not import model assembler."""

    def test_control_state_and_run_committer_protocols_exist(self) -> None:
        assert (ROOT / "lca/contracts/protocols/session/control_state.py").is_file()
        assert (ROOT / "lca/contracts/protocols/state/run_committer.py").is_file()

    def test_run_committer_is_reducer_subclass(self) -> None:
        """Wave C2: RunCommitter extends Reducer (alias contract)."""
        from lca.contracts.protocols.state.reducer import Reducer
        from lca.contracts.protocols.state.run_committer import RunCommitter

        assert issubclass(RunCommitter, Reducer)
        assert "commit_turn" in RunCommitter.__dict__ or any(
            "commit_turn" in base.__dict__ for base in RunCommitter.__mro__
        )

    def test_default_reducer_implements_commit_turn(self) -> None:
        """Wave C2: DefaultReducer exposes commit_turn (RunCommitter alias)."""
        from lca.plugins.loop.reducer.plugin import DefaultReducer

        reducer = DefaultReducer()
        assert callable(getattr(reducer, "commit_turn", None))

    def test_commit_turn_appends_turn_control_fact(self) -> None:
        """Wave C2: commit_turn routes fact append through Session (ADR-0186 SSOT)."""
        from lca.contracts.atoms.enums.enums import ActionType
        from lca.contracts.models.core.execution.decision import (
            Decision,
            Observation,
            ToolCall,
            Turn,
        )
        from lca.contracts.models.core.policy.budget import create_budget
        from lca.contracts.models.core.state.state import AgentState
        from lca.infrastructure.session.context.turn_control_reader import (
            projected_control_turns,
        )
        from lca.plugins.events.publishers._session_publish import (
            reset_publish_session,
            set_publish_session,
        )
        from lca.plugins.loop.reducer.plugin import DefaultReducer
        from lca.session.append import Session

        session = Session("wave_c2_smoke")
        token = set_publish_session(session)
        try:
            reducer = DefaultReducer()
            state = AgentState(
                trace_id="t",
                task="task",
                budget=create_budget(max_steps=8),
            )
            turn = Turn(
                decision=Decision(
                    decision_id="d-c2",
                    action_type=ActionType.USE_TOOL,
                    rationale="r",
                    confidence=1.0,
                    tool_calls=[
                        ToolCall(call_id="c1", tool_name="search", arguments={"q": "x"})
                    ],
                ),
                observation=Observation(
                    observation_id="o1",
                    success=True,
                    payload={"ok": True},
                ),
            )
            reducer.commit_turn(state, turn)
            projected = projected_control_turns(state)
            assert projected is not None
            assert len(projected) == 1
            assert projected[0].tool_name == "search"
        finally:
            reset_publish_session(token)

    def test_remember_phase_emits_turn_delta(self) -> None:
        """Wave C2: remember phase appends turn facts via the 'turn' RunDelta.

        The standard remember executor always emits a ``RunDelta`` with
        ``metadata['operation'] == 'turn'``; ``TurnDeltaHandler`` then
        routes it through ``reducer.commit_turn`` → ``Session.append``,
        so fact append is gated on the remember phase for every run
        whose remember phase executes.
        """
        src = (
            ROOT / "lca/plugins/loop/phase/remember/standard/plugin.py"
        ).read_text(encoding="utf-8")
        assert '"operation": "turn"' in src
        assert "decision" in src
        assert "observation" in src

        handler_src = (
            ROOT / "lca/plugins/act/delta/handlers_provider.py"
        ).read_text(encoding="utf-8")
        assert "commit_turn" in handler_src

    def test_gates_do_not_import_model_context_assembler(self) -> None:
        gates_dir = ROOT / "lca/cognition/brain/decision_gates"
        for path in gates_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue
            src = path.read_text(encoding="utf-8")
            assert "ModelContextAssembler" not in src
            assert "assemble_model_history" not in src

    def test_gates_do_not_read_state_history_directly(self) -> None:
        gates_dir = ROOT / "lca/cognition/brain/decision_gates"
        for path in gates_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue
            src = path.read_text(encoding="utf-8")
            assert "state.history" not in src


class TestTransportRecoveryAuthority:
    """I-RESUME-3: transport resume validates recover_live_agent authority."""

    def test_registry_commands_imports_transport_recovery(self) -> None:
        src = (
            ROOT
            / "lca/plugins/transport/webserver/handlers/runs/terminal/registry/commands.py"
        ).read_text(encoding="utf-8")
        assert "validate_durable_resume" in src
        assert "carrier.runs.resume" in src

    def test_recovery_public_api_exists(self) -> None:
        assert (ROOT / "lca" / "session" / "lifecycle" / "recovery.py").is_file()

    def test_runtime_loop_awaits_step_boundary(self) -> None:
        src = (ROOT / "lca/runtime/loop/runtime_loop.py").read_text(encoding="utf-8")
        assert "await_step_boundary_checkpoint" in src
