"""ADR-0191 runtime convergence invariants (skeleton).

Wave A–D 落地后逐步去 xfail。见 docs/adr/0191-runtime-loop-dsh-convergence-and-control-plane.md §10。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LCA_COGNITION = ROOT / "lca" / "cognition"
EXECUTOR = LCA_COGNITION / "brain" / "llm_turn" / "executor.py"
SAFE_EXECUTOR = LCA_COGNITION / "body" / "safe_executor.py"


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
        repair = ROOT / "lca" / "session" / "repair.py"
        assert repair.is_file()


class TestControlPlaneProtocols:
    """I-CONTROL-1: control protocols exist; gates do not import model assembler."""

    def test_control_state_and_run_committer_protocols_exist(self) -> None:
        assert (ROOT / "lca/contracts/protocols/session/control_state.py").is_file()
        assert (ROOT / "lca/contracts/protocols/state/run_committer.py").is_file()

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
            / "lca/plugins/transport/webserver/handlers/runs/terminal/registry_commands.py"
        ).read_text(encoding="utf-8")
        assert "validate_durable_resume" in src
        assert "carrier.runs.resume" in src

    def test_recovery_public_api_exists(self) -> None:
        assert (ROOT / "lca" / "session" / "recovery.py").is_file()
        assert (ROOT / "lca/plugins/session/runtime/transport_recovery.py").is_file()

    def test_runtime_loop_awaits_step_boundary(self) -> None:
        src = (ROOT / "lca/runtime/runtime_loop.py").read_text(encoding="utf-8")
        assert "await_step_boundary_checkpoint" in src
