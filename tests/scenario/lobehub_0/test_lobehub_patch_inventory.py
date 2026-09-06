"""LobeHub runtime patches at the 2026-08-21 journal-projector surface."""

from __future__ import annotations

from pathlib import Path

_PATCH_ROOT = Path("deploy/lobehub/patches")

_RUNTIME_SOURCES = {
    "LcaRunDriver.ts",
    "lcaFinishChat.ts",
    "lcaJournal.ts",
    "lcaChatRow.ts",
    "lcaPersist.ts",
    "lcaError.ts",
    "lcaArtifacts.ts",
    "lca_run_driver.py",
}


def test_runtime_patch_is_the_journal_driver() -> None:
    runtime = _PATCH_ROOT / "runtime"
    missing = [name for name in sorted(_RUNTIME_SOURCES) if not (runtime / name).is_file()]
    assert missing == [], missing
    assert not (runtime / "lca_agent_driver.py").is_file()
    assert not (runtime / "LcaAgentDriver.ts").is_file()
    hijack = (runtime / "lca_run_driver.py").read_text(encoding="utf-8")
    assert "runLcaJournal" in hijack
    assert "finishLcaChat" in hijack
    assert "await runLcaAgentTurn" not in hijack


def test_streaming_executor_hijack_is_run_lca_journal() -> None:
    for path in _PATCH_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "await runLcaAgentTurn" in text or "runLcaAgentTurn(this" in text:
            raise AssertionError(f"{path} injects runLcaAgentTurn")
