"""LobeHub runtime patches at the P1 gateway surface."""

from __future__ import annotations

from pathlib import Path

_PATCH_ROOT = Path("deploy/lobehub/patches")

_RUNTIME_SOURCES = {
    "lca_runtime_agent_gateway.py",
    "lca_runtime_chat_persistence.py",
    "lca_runtime_use_gateway_reconnect.py",
    "lcaChatRow.ts",
    "lcaFinishChat.ts",
    "lcaGateway/executeGatewayRun.ts",
}


def test_runtime_patch_is_gateway_driver() -> None:
    runtime = _PATCH_ROOT / "runtime"
    missing = [name for name in sorted(_RUNTIME_SOURCES) if not (runtime / name).is_file()]
    assert missing == [], missing
    assert not (runtime / "lca_run_driver.py").is_file()
    gateway = (runtime / "lca_runtime_agent_gateway.py").read_text(encoding="utf-8")
    assert "lcaExecuteGatewayRun" in gateway
    assert "runLcaJournal" not in gateway
