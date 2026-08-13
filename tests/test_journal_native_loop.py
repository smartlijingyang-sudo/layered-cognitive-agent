"""Contract: frontend projects Journal; LCA owns the agent loop."""

from __future__ import annotations

from pathlib import Path

_PATCHES = Path("deploy/lobehub/patches/runtime")
_DRIVER = (_PATCHES / "lca_run_driver.py").read_text(encoding="utf-8")


def test_fake_loop_patches_are_gone() -> None:
    assert not (_PATCHES / "journal_transport.py").exists()
    assert not (_PATCHES / "lca_resolved_tools.py").exists()
    assert not (_PATCHES / "call_llm_finalizer.py").exists()
    assert "lcaClosedLoop" not in _DRIVER
    assert "new GeneralChatAgent" not in _DRIVER
    assert "new LcaResolvedToolTransport" not in _DRIVER
    assert "runAttempt" not in _DRIVER
    assert "lcaCursor" not in _DRIVER
    customizations = Path("deploy/lobehub/CUSTOMIZATIONS.md").read_text(encoding="utf-8")
    assert "| `journal_transport`" not in customizations
    assert "| `lca_resolved_tools`" not in customizations
    assert "| `lca_run_driver`" in customizations


def test_driver_projects_one_run() -> None:
    assert "export async function runLcaJournal" in _DRIVER
    assert "POST" in _DRIVER
    assert "/lca-api/runs" in _DRIVER
    assert "/live" in _DRIVER
    assert "Last-Event-ID" in _DRIVER
    assert "LlmCallStarted" in _DRIVER
    assert "openTurn" in _DRIVER


def test_new_llm_call_opens_new_handler() -> None:
    assert "case 'LlmCallStarted'" in _DRIVER
    assert "await openTurn(" in _DRIVER
    assert "new StreamingHandler" in _DRIVER


def test_hooks_streaming_executor_not_runtime_host() -> None:
    assert "streamingExecutor.ts" in _DRIVER
    assert "runLcaJournal" in _DRIVER
    assert "buildClientRuntimeHost" not in _DRIVER
    assert "GeneralChatAgent.ts" not in _DRIVER
    assert "llm: new" not in _DRIVER


def test_driver_splits_parse_project_turn() -> None:
    assert "function parseSseBlock" in _DRIVER
    assert "function projectJournalFrame" in _DRIVER
    assert "async function openTurn" in _DRIVER or "const openTurn" in _DRIVER


def test_finished_is_not_live_eof() -> None:
    """Artifact closure is recorded after *Finished; keep reading until tail closes."""
    consume = _DRIVER.split("for await (const frame of readSse")[1].split("const snapRes")[0]
    assert "AgentRunFinished" not in consume
    assert "TeamRunFinished" not in consume
    assert "finished = true" not in _DRIVER


def test_cancel_sends_authorization() -> None:
    cancel_call = _DRIVER.split("/cancel")[0][-120:] + _DRIVER.split("/cancel")[1][:180]
    assert "authHeaders" in cancel_call
    assert "method: 'POST'" in cancel_call


def test_unknown_tool_is_not_silent() -> None:
    assert "console.warn('lca: unknown tool'" in _DRIVER


def test_sse_parser_reads_id_and_multiline_data() -> None:
    assert "line.startsWith('id:')" in _DRIVER or "line.startsWith('id: ')" in _DRIVER
    assert "dataLines" in _DRIVER or "data: " in _DRIVER


def test_live_gap_is_explicit() -> None:
    assert "case 'LiveGap'" in _DRIVER


def test_driver_does_not_invent_hil_or_hop_bus() -> None:
    assert "hopLog" not in _DRIVER
    assert "waitWhileWaiting" not in _DRIVER
    assert "postAnswer" not in _DRIVER
    assert "/answer" not in _DRIVER


def test_tool_denied_matches_invocation_id() -> None:
    denied = _DRIVER.split("case 'tool-denied'")[1].split("case ")[0]
    assert "findTurnTool" in denied


def test_abort_posts_cancel() -> None:
    assert "/cancel" in _DRIVER
    assert "method: 'POST'" in _DRIVER
