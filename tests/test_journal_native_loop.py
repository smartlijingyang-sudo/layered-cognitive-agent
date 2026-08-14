"""Contract: frontend projects Journal onto the native LobeHub message graph."""

from __future__ import annotations

from pathlib import Path

_RUNTIME = Path("deploy/lobehub/patches/runtime")
_DRIVER_PY = (_RUNTIME / "lca_run_driver.py").read_text(encoding="utf-8")
_DRIVER_TS = (_RUNTIME / "LcaRunDriver.ts").read_text(encoding="utf-8")
_JOURNAL_TS = (_RUNTIME / "lcaJournal.ts").read_text(encoding="utf-8")
_ART_TS = (_RUNTIME / "lcaArtifacts.ts").read_text(encoding="utf-8")
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
    assert (_RUNTIME / "lcaJournal.ts").is_file()
    assert (_RUNTIME / "lcaArtifacts.ts").is_file()
    assert (_RUNTIME / "lcaFinishChat.ts").is_file()
    assert (_RUNTIME / "lcaChatRow.ts").is_file()


def test_python_only_copies_and_hooks() -> None:
    assert "write_if_changed" in _DRIVER_PY
    assert "render_wire_ts" in _DRIVER_PY
    assert "finishLcaChat" in _DRIVER_PY
    assert "lcaJournal.ts" in _DRIVER_PY
    assert "lcaArtifacts.ts" in _DRIVER_PY
    assert "refreshMessages" not in _DRIVER_PY


def test_driver_sends_execution_plane() -> None:
    assert "function planeFieldsFromAgent" in _DRIVER_TS
    assert "...planeFieldsFromAgent(ctx.agentId)" in _DRIVER_TS
    assert "plane: 'machine'" in _DRIVER_TS
    assert "plane: 'sandbox'" in _DRIVER_TS


def test_driver_projects_one_run() -> None:
    assert "POST" in _DRIVER_TS
    assert "/lca-api/runs" in _DRIVER_TS
    assert "/live" in _DRIVER_TS
    assert "Last-Event-ID" in _DRIVER_TS
    assert "LlmCallStarted" in _JOURNAL_TS
    assert "const openTurn" in _DRIVER_TS


def test_each_llm_call_opens_an_assistant() -> None:
    assert "await openTurn(projected.speaker)" in _DRIVER_TS
    assert "handler = makeHandler(assistantId);\n      return" not in _DRIVER_TS
    assert "lastResultMsgId" in _DRIVER_TS
    assert "lastResultMsgId || prevAssistant" in _DRIVER_TS
    assert "role: 'assistant'" in _DRIVER_TS
    assert "new StreamingHandler" in _DRIVER_TS
    assert "ensureSpeaker" not in _DRIVER_TS


def test_deleted_file_universe() -> None:
    assert "attachNativeFiles" not in _DRIVER_TS
    assert "uploadWithProgress" not in _DRIVER_TS
    assert "addFilesToMessage" not in _DRIVER_TS
    assert "latestDeliverables(turnImages)" not in _DRIVER_TS


def test_tools_are_native_child_messages() -> None:
    assert "role: 'tool'" in _DRIVER_TS
    assert "result_msg_id" in _DRIVER_TS
    assert "type: 'toolCalling'" in _DRIVER_TS
    assert "completeOperation" in _DRIVER_TS
    assert "optimisticUpdatePluginState" in _DRIVER_TS


def test_tool_call_streaming_opens_the_same_card() -> None:
    assert "case 'ToolCallStreaming'" in _JOURNAL_TS
    assert "existing.call.function.arguments" in _DRIVER_TS
    assert "function toolCardContent" in _DRIVER_TS
    assert "result_preview" not in _DRIVER_TS
    assert "result_preview" not in _JOURNAL_TS


def test_result_keys_keep_code_out_of_omit() -> None:
    assert "const RESULT_KEYS" in _DRIVER_TS
    assert "function pickArgs" in _DRIVER_TS
    assert "ARG_OMIT" not in _DRIVER_TS
    assert "hasRenderableArgs" not in _DRIVER_TS
    start = _DRIVER_TS.index("const RESULT_KEYS")
    block = _DRIVER_TS[start : _DRIVER_TS.index("];", start) + 2]
    assert "'code'" not in block
    assert "'executionEnv'" in block
    assert "'output'" in block
    assert "'files'" in block
    assert "'downloadUrl'" in block


def test_reasoning_completed_closes_thinking() -> None:
    assert "case 'ReasoningCompleted'" in _JOURNAL_TS
    assert "kind: 'reasoning-end'" in _JOURNAL_TS
    assert "case 'reasoning-end'" in _DRIVER_TS
    assert "journalDurationMs" in _DRIVER_TS


def test_artifacts_rewrite_relative_markdown() -> None:
    assert "export function rewriteArtifactMarkdown" in _ART_TS
    assert "export function collectArtifactFiles" in _ART_TS
    assert "rewriteArtifactMarkdown" in _DRIVER_TS
    assert "sandbox:" in _ART_TS
    assert "computer:" in _ART_TS


def test_unfinished_tools_are_sealed_before_next_turn() -> None:
    assert "const sealOpenTools" in _DRIVER_TS
    finish = _DRIVER_TS.split("const finishTurn = async () => {", 1)[1].split("};", 1)[0]
    assert "sealOpenTools()" in finish
    seal = _DRIVER_TS.split("const sealOpenTools", 1)[1].split("const finishTurn", 1)[0]
    assert "completeOperation" in seal
    assert "publishTurnTools(false)" in seal


def test_file_list_gateway_preview_patch_exists() -> None:
    patch = Path("deploy/lobehub/patches/ui/file_list_gateway_preview.py").read_text(
        encoding="utf-8"
    )
    customizations = Path("deploy/lobehub/CUSTOMIZATIONS.md").read_text(encoding="utf-8")
    assert "LCA: gateway /files preview" in patch
    assert "| `file_list_gateway_preview`" in customizations
    assert "window.open" in patch


def test_final_answer_gets_native_deliverable_lists() -> None:
    persist = _DRIVER_TS.split("const persistRow = async () => {", 1)[1].split("const sealRow", 1)[
        0
    ]
    assert "toImageList" in persist
    assert "toFileList" in persist
    assert "imageList" in persist
    assert "fileList" in persist
    assert "currentTurnTools.length === 0" in persist
    assert "publishFinalDeliverables" in _DRIVER_TS


def test_tool_stream_updates_go_through_handler() -> None:
    assert "type: 'tool_calls'" in _DRIVER_TS
    assert "JSON.stringify(pickArgs(projected.state))" in _DRIVER_TS


def test_hooks_streaming_executor_not_runtime_host() -> None:
    assert "streamingExecutor.ts" in _DRIVER_PY
    assert "runLcaJournal" in _DRIVER_PY
    assert "buildClientRuntimeHost" not in _DRIVER_PY
    assert "GeneralChatAgent.ts" not in _DRIVER_PY


def test_driver_splits_parse_project_seal() -> None:
    assert "export function parseSseBlock" in _JOURNAL_TS
    assert "export function projectJournalFrame" in _JOURNAL_TS
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
    assert "line.startsWith('id:')" in _JOURNAL_TS or "line.startsWith('id: ')" in _JOURNAL_TS
    assert "dataLines" in _JOURNAL_TS


def test_live_gap_is_explicit() -> None:
    assert "case 'LiveGap'" in _JOURNAL_TS


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


def test_invoke_does_not_rewrite_arguments() -> None:
    invoked = _DRIVER_TS.split("case 'tool-invoked'")[1].split("case ")[0]
    assert "function.arguments" not in invoked
    assert "optimisticUpdatePluginState" in invoked
