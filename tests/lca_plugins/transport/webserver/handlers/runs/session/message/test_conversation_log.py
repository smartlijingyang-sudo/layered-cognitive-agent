"""Regression tests for defect-1 fix: backend conversation log + gap-fill.

Covers:
1. gap-fill restores a missing assistant turn from the per-topic log
2. log append keeps only the newest 50 pairs
3. log I/O failure never raises
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.plugins.transport.webserver.handlers.runs.session.message.conversation_log import (
    MAX_STORED_PAIRS,
    append_conversation_turn,
    conversation_log_path,
    fill_history_gaps,
    find_assistant_reply,
    normalize_text,
)
from lca.plugins.transport.webserver.handlers.runs.session.message.history import (
    extract_prior_turns,
)
from lca.plugins.transport.webserver.handlers.runs.terminal.lifecycle import (
    RunTerminalizer,
)


def _plain(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    return ""


def _msg(role: str, text: str) -> dict[str, Any]:
    return {"role": role, "content": text}


def _roles(turns: tuple[ConversationTurn, ...]) -> list[tuple[str, str]]:
    return [(t.role, t.content) for t in turns]


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  hello \n  world\t! ") == "hello world !"


def test_gap_fill_restores_missing_assistant_turn(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    append_conversation_turn(
        assistant_home=home,
        topic_id="t1",
        user_text="把名字改成大内管家",
        assistant_text="已改名为大内管家",
    )
    turns = extract_prior_turns(
        [_msg("user", "把名字改成大内管家"), _msg("user", "用 markdown 展示")],
        plain_text_fn=_plain,
        assistant_home=home,
        topic_id="t1",
    )
    assert _roles(turns) == [
        ("user", "把名字改成大内管家"),
        ("assistant", "已改名为大内管家"),
    ]


def test_gap_fill_no_log_match_drops_orphaned_user_turn(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    turns = extract_prior_turns(
        [_msg("user", "第一句"), _msg("user", "第二句")],
        plain_text_fn=_plain,
        assistant_home=home,
        topic_id="t-no-such",
    )
    assert _roles(turns) == []


def test_gap_fill_no_log_match_preserves_earlier_completed_turns(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    turns = extract_prior_turns(
        [
            _msg("user", "已完成提问"),
            _msg("assistant", "已完成回答"),
            _msg("user", "失败提问"),
            _msg("user", "当前提问"),
        ],
        plain_text_fn=_plain,
        assistant_home=home,
        topic_id="t-no-such",
    )
    assert _roles(turns) == [
        ("user", "已完成提问"),
        ("assistant", "已完成回答"),
    ]


def test_gap_fill_disabled_without_topic_id(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    append_conversation_turn(
        assistant_home=home, topic_id="t1", user_text="第一句", assistant_text="回复一"
    )
    # legacy call shape: no assistant_home/topic_id -> no lookup attempted
    # Trailing un-replied user messages are dropped to prevent leakage
    turns = extract_prior_turns(
        [_msg("user", "第一句"), _msg("user", "第二句")],
        plain_text_fn=_plain,
    )
    assert _roles(turns) == []


def test_gap_fill_matches_normalized_text(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    append_conversation_turn(
        assistant_home=home, topic_id="t1", user_text="hello   world", assistant_text="hi there"
    )
    assert (
        find_assistant_reply(assistant_home=home, topic_id="t1", user_text="hello\nworld")
        == "hi there"
    )


def test_gap_fill_prefers_newest_pair(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    append_conversation_turn(
        assistant_home=home, topic_id="t1", user_text="q", assistant_text="old"
    )
    append_conversation_turn(
        assistant_home=home, topic_id="t1", user_text="q", assistant_text="new"
    )
    assert find_assistant_reply(assistant_home=home, topic_id="t1", user_text="q") == "new"


def test_topic_id_sanitized_against_traversal(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    path = conversation_log_path(home, "../../etc/passwd")
    assert path.parent == home / "conversations"
    assert ".." not in path.name


def test_append_keeps_only_last_50_pairs(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    for i in range(MAX_STORED_PAIRS + 5):
        append_conversation_turn(
            assistant_home=home, topic_id="t1", user_text=f"q{i}", assistant_text=f"a{i}"
        )
    lines = conversation_log_path(home, "t1").read_text(encoding="utf-8").splitlines()
    assert len(lines) == MAX_STORED_PAIRS
    assert json.loads(lines[0])["user"] == "q5"  # first 5 evicted
    assert json.loads(lines[-1])["user"] == f"q{MAX_STORED_PAIRS + 4}"


def test_append_failure_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "asst"

    def _boom(self: Path, *args: Any, **kwargs: Any) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(Path, "mkdir", _boom)
    # must not raise even when the directory cannot be created
    append_conversation_turn(assistant_home=home, topic_id="t1", user_text="q", assistant_text="a")


def test_fill_history_gaps_skips_corrupt_lines(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    path = conversation_log_path(home, "t1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('not json\n{"user": "q", "assistant": "a"}\n{"user": 123}\n', encoding="utf-8")
    assert find_assistant_reply(assistant_home=home, topic_id="t1", user_text="q") == "a"


def test_fill_history_gaps_direct(tmp_path: Path) -> None:
    home = tmp_path / "asst"
    append_conversation_turn(
        assistant_home=home, topic_id="t1", user_text="u1", assistant_text="a1"
    )
    turns = [
        ConversationTurn(role="user", content="u1"),
        ConversationTurn(role="user", content="u2"),
    ]
    filled = fill_history_gaps(turns, assistant_home=home, topic_id="t1")
    assert [(t.role, t.content) for t in filled] == [
        ("user", "u1"),
        ("assistant", "a1"),
        ("user", "u2"),
    ]


def _terminal_session(**kwargs: Any) -> Any:
    session = MagicMock()
    session.run_id = "run-conv-log"
    session.hub = None
    session.cancel_requested = False
    session.error = ""
    session.assistant_id = kwargs.get("assistant_id", "asst_1")
    session.topic_id = kwargs.get("topic_id", "topic_1")
    session.user_text = kwargs.get("user_text", "把名字改成大内管家")
    session.output = kwargs.get("output", "已改名为大内管家")
    return session


@pytest.mark.asyncio
async def test_terminalize_appends_conversation_log_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("lca.infrastructure.path.locator.get_lca_home", lambda: tmp_path)
    session = _terminal_session()
    registry = MagicMock()

    async def _finalize(_run_id: str) -> None:
        return None

    await RunTerminalizer(registry, finalizer=_finalize, materializer=lambda _s: None).terminalize(
        session, success=True
    )

    path = tmp_path / "assistants" / "asst_1" / "conversations" / "topic_1.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record == {"user": "把名字改成大内管家", "assistant": "已改名为大内管家"}


@pytest.mark.asyncio
async def test_terminalize_skips_log_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("lca.infrastructure.path.locator.get_lca_home", lambda: tmp_path)
    session = _terminal_session()
    registry = MagicMock()

    async def _finalize(_run_id: str) -> None:
        return None

    await RunTerminalizer(registry, finalizer=_finalize, materializer=lambda _s: None).terminalize(
        session, success=False
    )

    path = tmp_path / "assistants" / "asst_1" / "conversations" / "topic_1.jsonl"
    assert not path.exists()


@pytest.mark.asyncio
async def test_terminalize_skips_log_without_topic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("lca.infrastructure.path.locator.get_lca_home", lambda: tmp_path)
    session = _terminal_session(topic_id="")
    registry = MagicMock()

    async def _finalize(_run_id: str) -> None:
        return None

    await RunTerminalizer(registry, finalizer=_finalize, materializer=lambda _s: None).terminalize(
        session, success=True
    )

    assert not (tmp_path / "assistants").exists()
