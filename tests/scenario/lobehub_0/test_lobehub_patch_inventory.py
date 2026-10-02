"""LobeHub runtime patches at the P1 gateway surface."""

from __future__ import annotations

from pathlib import Path

_PATCH_ROOT = Path("deploy/lobehub/patches")

_RUNTIME_SOURCES = {
    "lca_runtime_agent_gateway.py",
    "lca_runtime_chat_persistence.py",
    "lca_runtime_use_gateway_reconnect.py",
    "lca_assistant_events.py",
    "lcaChatRow.ts",
    "lcaFinishChat.ts",
    "lcaGateway/executeGatewayRun.ts",
    "lcaGateway/assistantEventClient.ts",
}


def test_runtime_patch_is_gateway_driver() -> None:
    runtime = _PATCH_ROOT / "runtime"
    missing = [name for name in sorted(_RUNTIME_SOURCES) if not (runtime / name).is_file()]
    assert missing == [], missing
    assert not (runtime / "lca_run_driver.py").is_file()
    gateway = (runtime / "lca_runtime_agent_gateway.py").read_text(encoding="utf-8")
    assert "lcaExecuteGatewayRun" in gateway
    assert "runLcaJournal" not in gateway


def test_lca_assistant_events_registered() -> None:
    from deploy.lobehub.engine import discover_patches

    runtime = _PATCH_ROOT / "runtime"
    names = {pm.meta.name for pm in discover_patches()}
    assert "lca_assistant_events" in names
    events = (runtime / "lca_assistant_events.py").read_text(encoding="utf-8")
    assert "assistantEventClient" in events
    client = (runtime / "lcaGateway" / "assistantEventClient.ts").read_text(encoding="utf-8")
    assert "lca-assistant-avatar-changed" in client
