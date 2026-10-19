"""RA-166: the twin derive_messages agree on the three adjudicated forks.

Writer path: ``RunSessionWriter.derive_messages()`` — journal walk,
orphan-drop + ``orphan_dropped_count`` (the LLM wire in
``think.history.assemble``).

Fold SSOT path: ``Session.derive_messages()`` — kernel ``foldSurface``
pure function + ``derive_event_message`` per node (shared with the
``model_visible`` projection increment and ``token_usage``).

Adjudicated semantics (recorded in the RA-166 commit body):
- fork 1 orphan-drop: writer drops orphans; the fold SSOT does not
  (documented shim difference — transcript/history reads must not
  silently delete rows).
- fork 2 assistant tool_calls: declaring rows are kept on BOTH paths,
  even when content is empty/None (OpenAI FC requires the declaring
  message; ADR-0201 MV2).
- fork 3 empty tool result: ``"[tool_result] (no output)"`` on BOTH
  paths, decided once at write time by ``build_openai_tool_result_message``.
"""

from __future__ import annotations

from lca.runtime.session.run_session_writer import RunSessionWriter
from lca.session.append import Session


def _writer_with_turn() -> tuple[Session, RunSessionWriter]:
    session = Session("ra166_parity")
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    return session, writer


def _declaring_assistant(writer: RunSessionWriter, call_id: str = "X") -> None:
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": call_id, "name": "bash", "arguments": "{}"}],
        usage=None,
    )


def test_declaring_assistant_kept_on_both_paths() -> None:
    """Fork 2: assistant declaring tool_calls survives on both derives."""
    session, writer = _writer_with_turn()
    _declaring_assistant(writer)
    writer.append_tool_result(turn=0, step=0, call_id="X", content="ok", error=None, meta=None)

    writer_msgs = writer.derive_messages()
    fold_msgs = session.derive_messages()

    assert [m["role"] for m in writer_msgs] == ["user", "assistant", "tool"]
    assert [m["role"] for m in fold_msgs] == ["user", "assistant", "tool"]
    # The declaring assistant row keeps its tool_calls on both paths.
    assert writer_msgs[1]["tool_calls"] == [{"id": "X", "name": "bash", "arguments": "{}"}]
    assert fold_msgs[1]["tool_calls"] == [{"id": "X", "name": "bash", "arguments": "{}"}]
    assert fold_msgs[1]["role"] == "assistant"


def test_empty_tool_result_placeholder_on_both_paths() -> None:
    """Fork 3: empty tool result shows the placeholder on both derives."""
    session, writer = _writer_with_turn()
    _declaring_assistant(writer)
    writer.append_tool_result(turn=0, step=0, call_id="X", content="", error=None, meta=None)

    writer_msgs = writer.derive_messages()
    fold_msgs = session.derive_messages()

    assert writer_msgs[-1]["content"] == "[tool_result] (no output)"
    assert fold_msgs[-1]["content"] == "[tool_result] (no output)"
    assert fold_msgs[-1]["role"] == "tool"
    assert fold_msgs[-1]["tool_call_id"] == "X"


def test_orphan_dropped_only_on_writer_path() -> None:
    """Fork 1: orphan-drop is the writer shim's wire-safety step.

    The fold SSOT keeps the orphan row (documented difference): transcript
    and history reads must not silently delete journal rows.
    """
    session, writer = _writer_with_turn()
    _declaring_assistant(writer, call_id="X")
    writer.append_tool_result(turn=0, step=0, call_id="Y", content="orphan", error=None, meta=None)

    writer_msgs = writer.derive_messages()
    fold_msgs = session.derive_messages()

    assert [m["role"] for m in writer_msgs] == ["user", "assistant"]
    assert writer.orphan_dropped_count == 1
    assert [m["role"] for m in fold_msgs] == ["user", "assistant", "tool"]
    assert fold_msgs[-1]["tool_call_id"] == "Y"
