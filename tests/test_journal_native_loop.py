"""Contract: frontend projects Journal; LCA owns the agent loop."""

from __future__ import annotations

from pathlib import Path

_RUNTIME = Path("deploy/lobehub/patches/runtime")
_DRIVER_PY = (_RUNTIME / "lca_run_driver.py").read_text(encoding="utf-8")
_DRIVER_TS = (_RUNTIME / "LcaRunDriver.ts").read_text(encoding="utf-8")
_ROW_TS = (_RUNTIME / "lcaChatRow.ts").read_text(encoding="utf-8")
_FINISH_TS = (_RUNTIME / "lcaFinishChat.ts").read_text(encoding="utf-8")


def test_fake_loop_patches_are_gone() -> None:
    assert not (_RUNTIME / "journal_transport.py").exists()
    assert not (_RUNTIME / "lca_resolved_tools.py").exists()
    assert not (_RUNTIME / "call_llm_finalizer.py").exists()
    assert "lcaClosedLoop" not in _DRIVER_PY
    assert "new GeneralChatAgent" not in _DRIVER_TS
    customizations = Path("deploy/lobehub/CUSTOMIZATIONS.md").read_text(encoding="utf-8")
    assert "| `journal_transport`" not in customizations
    assert "| `lca_run_driver`" in customizations


def test_implementation_is_typescript() -> None:
    assert "_DRIVER_TEMPLATE" not in _DRIVER_PY
    assert "export async function runLcaJournal" in _DRIVER_TS
    assert "export async function finishLcaChat" in _FINISH_TS
    assert (_RUNTIME / "LcaRunDriver.ts").is_file()
    assert (_RUNTIME / "lcaFinishChat.ts").is_file()
    assert (_RUNTIME / "lcaChatRow.ts").is_file()


def test_python_only_copies_and_hooks() -> None:
    assert "write_if_changed" in _DRIVER_PY
    assert "render_wire_ts" in _DRIVER_PY
    assert "finishLcaChat" in _DRIVER_PY
    assert "refreshMessages" not in _DRIVER_PY


def test_driver_projects_one_run() -> None:
    assert "POST" in _DRIVER_TS
    assert "/lca-api/runs" in _DRIVER_TS
    assert "/live" in _DRIVER_TS
    assert "Last-Event-ID" in _DRIVER_TS
    assert "LlmCallStarted" in _DRIVER_TS
    assert "ensureSpeaker" in _DRIVER_TS


def test_one_speaker_one_row() -> None:
    assert "case 'LlmCallStarted'" in _DRIVER_TS
    assert "sameSpeaker" in _DRIVER_TS
    assert "optimisticUpdateMessageContent" in _DRIVER_TS
    assert "new StreamingHandler" in _DRIVER_TS
    assert "if (handler && (sawContent || turnTools.length > 0)) await openTurn()" not in _DRIVER_TS


def test_open_turn_is_speaker_not_llm_call() -> None:
    assert "kind: 'open-turn'; speaker: string" in _DRIVER_TS
    assert "scope.agent_role" in _DRIVER_TS


def test_hooks_streaming_executor_not_runtime_host() -> None:
    assert "streamingExecutor.ts" in _DRIVER_PY
    assert "runLcaJournal" in _DRIVER_PY
    assert "buildClientRuntimeHost" not in _DRIVER_PY
    assert "GeneralChatAgent.ts" not in _DRIVER_PY


def test_driver_splits_parse_project_seal() -> None:
    assert "function parseSseBlock" in _DRIVER_TS
    assert "function projectJournalFrame" in _DRIVER_TS
    assert "const openRow" in _DRIVER_TS
    assert "const persistRow" in _DRIVER_TS
    assert "const sealRow" in _DRIVER_TS


def test_finished_is_not_live_eof() -> None:
    consume = _DRIVER_TS.split("for await (const frame of readSse")[1].split("const snapRes")[0]
    assert "AgentRunFinished" not in consume
    assert "TeamRunFinished" not in consume
    assert "finished = true" not in _DRIVER_TS


def test_cancel_sends_authorization() -> None:
    cancel_call = _DRIVER_TS.split("/cancel")[0][-120:] + _DRIVER_TS.split("/cancel")[1][:180]
    assert "authHeaders" in cancel_call
    assert "method: 'POST'" in cancel_call


def test_unknown_tool_is_not_silent() -> None:
    assert "console.warn('lca: unknown tool'" in _DRIVER_TS


def test_sse_parser_reads_id_and_multiline_data() -> None:
    assert "line.startsWith('id:')" in _DRIVER_TS or "line.startsWith('id: ')" in _DRIVER_TS
    assert "dataLines" in _DRIVER_TS


def test_live_gap_is_explicit() -> None:
    assert "case 'LiveGap'" in _DRIVER_TS


def test_driver_does_not_invent_hil_or_hop_bus() -> None:
    assert "hopLog" not in _DRIVER_TS
    assert "waitWhileWaiting" not in _DRIVER_TS
    assert "postAnswer" not in _DRIVER_TS
    assert "/answer" not in _DRIVER_TS


def test_tool_denied_matches_invocation_id() -> None:
    denied = _DRIVER_TS.split("case 'tool-denied'")[1].split("case ")[0]
    assert "findTurnTool" in denied


def test_abort_posts_cancel() -> None:
    assert "/cancel" in _DRIVER_TS
    assert "method: 'POST'" in _DRIVER_TS


def test_finish_is_lobehub_chrome_not_runtime() -> None:
    assert "Not AgentRuntime" in _FINISH_TS
    assert "refreshMessages" not in _FINISH_TS
    assert "completeRun" in _FINISH_TS
    assert "persistMissed" in _FINISH_TS


def test_seal_retries_when_store_still_placeholder() -> None:
    assert "persistMissed" in _DRIVER_TS
    assert "persist missed, retrying" in _DRIVER_TS
    assert "ASSISTANT_PLACEHOLDER = '...'" in _ROW_TS
