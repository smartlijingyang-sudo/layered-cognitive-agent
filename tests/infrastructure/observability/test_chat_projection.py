"""Chat projection ids and the writes a refresh reads."""

from __future__ import annotations

import json
from types import SimpleNamespace

from lca.infrastructure.observability.chat_projection import (
    ChatIdentity,
    ask_message_id,
    clear_pending_question,
    final_message_id,
    identity_from_session,
    pending_question,
    resolve_identity,
    terminal_reply_text,
    write_final_reply,
    write_pending_question,
)


class _Cursor:
    def __init__(
        self,
        parent: str | None = "user-msg",
        queue: list[tuple | None] | None = None,
    ) -> None:
        self.parent = parent
        self.queue = list(queue) if queue is not None else None
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.calls.append((sql, params))

    def fetchone(self) -> tuple | None:
        if self.queue is not None:
            return self.queue.pop(0) if self.queue else None
        if self.parent is None:
            return None
        return (self.parent,)

    def fetchall(self) -> list:
        if self.queue is not None and self.queue and isinstance(self.queue[0], list):
            return self.queue.pop(0)
        return []


def _identity() -> ChatIdentity:
    return ChatIdentity(
        run_id="run_abc",
        user_id="local-dev-user",
        topic_id="tpc_1",
        agent_id="agt_1",
    )


def test_identity_requires_a_topic_and_can_fill_solo_later() -> None:
    session = SimpleNamespace(
        run_id="run_abc",
        user_id="",
        topic_id="",
        agent=SimpleNamespace(agent_id="solo"),
    )
    assert identity_from_session(session) is None

    session.topic_id = "tpc_1"
    partial = identity_from_session(session)
    assert partial is not None
    assert partial.agent_id == "solo"
    assert partial.user_id == ""

    class _TopicCursor(_Cursor):
        def fetchone(self) -> tuple | None:
            return ("local-dev-user", "agt_1")

    resolved = resolve_identity(_TopicCursor(), partial)
    assert resolved == _identity()


def test_pending_question_reads_the_first_tool_call() -> None:
    assert pending_question(None) is None
    assert pending_question({"questions": []}) is None
    call_id, questions = pending_question(
        {
            "questions": [{"header": "名字"}],
            "tool_calls": [{"call_id": "toolu_1", "tool_name": "askUserQuestion"}],
        }
    )
    assert call_id == "toolu_1"
    assert questions == [{"header": "名字"}]


def test_final_reply_uses_one_id_and_skips_blank_text() -> None:
    identity = _identity()
    blank = _Cursor()
    assert write_final_reply(blank, identity, "   ") is None
    assert blank.calls == []

    cur = _Cursor(queue=[[], ("user-msg",), [], ("user-msg",)])
    assert write_final_reply(cur, identity, "小讯已创建") == "lca-final-run_abc"
    assert write_final_reply(cur, identity, "小讯已创建") == final_message_id("run_abc")
    inserts = [(sql, params) for sql, params in cur.calls if "INSERT INTO messages" in sql]
    assert len(inserts) == 2
    assert all("ON CONFLICT (id)" in sql for sql, _ in inserts)
    assert inserts[0][1][0] == "lca-final-run_abc"
    assert inserts[1][1][0] == "lca-final-run_abc"
    assert inserts[1][1][2] == "小讯已创建"


def test_final_reply_adopts_the_client_row_instead_of_inserting() -> None:
    cur = _Cursor(queue=[[("A1r1R41z", "小讯已创建")]])
    assert write_final_reply(cur, _identity(), "小讯已创建") == "A1r1R41z"
    assert not any("INSERT INTO messages" in sql for sql, _ in cur.calls)

    hollow = _Cursor(queue=[[("A1r1R41z", "...")]])
    assert write_final_reply(hollow, _identity(), "小讯已创建") == "A1r1R41z"
    updates = [params for sql, params in hollow.calls if "UPDATE messages" in sql]
    assert updates and updates[0][0] == "小讯已创建"


def test_pending_question_updates_the_client_tool_row() -> None:
    cur = _Cursor(queue=[("spOxX6Rs",)])
    found = write_pending_question(
        cur,
        _identity(),
        tool_call_id="toolu_1",
        questions=[{"header": "角色"}],
    )
    assert found == "spOxX6Rs"
    assert not any("INSERT INTO messages" in sql for sql, _ in cur.calls)
    updates = [sql for sql, _ in cur.calls if "UPDATE message_plugins" in sql]
    assert len(updates) == 1


def test_pending_question_row_is_stable_across_a_second_pause() -> None:
    identity = _identity()
    cur = _Cursor(queue=[None, ("asst-1",), None, ("asst-1",)])
    first = write_pending_question(
        cur,
        identity,
        tool_call_id="toolu_1",
        questions=[{"header": "角色"}],
    )
    second = write_pending_question(
        cur,
        identity,
        tool_call_id="toolu_2",
        questions=[{"header": "名字"}],
    )
    assert first == second == ask_message_id("run_abc")
    plugin_writes = [params for sql, params in cur.calls if "INSERT INTO message_plugins" in sql]
    assert plugin_writes[0][1] == "toolu_1"
    assert plugin_writes[1][1] == "toolu_2"
    assert '"status": "pending"' in plugin_writes[1][6]


def test_terminal_reply_text_reads_the_journal_when_output_is_empty(tmp_path) -> None:
    journal = tmp_path / "journal.json"
    journal.write_text(
        json.dumps(
            {
                "steps": [
                    {"thinking": {"decision": "use_tool", "raw_response_preview": "先提问"}},
                    {
                        "thinking": {
                            "decision": "respond",
                            "raw_response_preview": "收到，红茶已记",
                        }
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    session = SimpleNamespace(output="  ", spine_path=tmp_path / "run.spine.jsonl")
    assert terminal_reply_text(session) == "收到，红茶已记"
    session.output = "session wins"
    assert terminal_reply_text(session) == "session wins"


def test_clear_pending_question_marks_the_client_row_for_the_run() -> None:
    cur = _Cursor()
    clear_pending_question(cur, _identity(), approved=True)
    sql, params = cur.calls[0]
    assert "state->'lca'->>'run_id'" in sql
    assert params[3] == "lca-ask-run_abc"
    assert params[4] == "run_abc"
    assert '"status": "approved"' in params[0]
