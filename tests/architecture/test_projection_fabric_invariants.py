"""ADR-0193 projection fabric architecture guards."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COGNITION = ROOT / "lca" / "cognition"
EXECUTOR = COGNITION / "brain" / "llm_turn" / "executor.py"


def test_cognition_production_has_no_build_tool_history() -> None:
    for path in COGNITION.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "build_tool_history" not in src, f"{path} still references build_tool_history"


def test_executor_uses_assembler_not_derive_messages() -> None:
    src = EXECUTOR.read_text(encoding="utf-8")
    assert "assemble_model_history" in src
    assert "derive_messages" not in src


def test_session_derive_messages_uses_projection_fabric() -> None:
    src = (ROOT / "lca" / "session" / "append.py").read_text(
        encoding="utf-8"
    )
    assert "model_visible_messages" in src


def test_messages_no_v1_fallback() -> None:
    src = (ROOT / "lca" / "plugins" / "session" / "runtime" / "messages.py").read_text(
        encoding="utf-8"
    )
    assert "message.accepted.v1" not in src
    assert "assistant.responded.v1" not in src
