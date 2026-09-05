"""Wave 1: 撕尾半行不暴露（验收 #7）。"""

from __future__ import annotations

import json
from pathlib import Path

from lca.plugins.session.runtime.log_reader import iter_session_log_lines, load_session_events


def test_torn_tail_line_ignored(tmp_path: Path) -> None:
    good = json.dumps({"type": "turn.started.v1", "seq": 0, "time": 1, "data": {"turn": 1}})
    torn = '{"type": "turn.ended.v1", "seq": 1, "time": 2, "data": {"turn": 1, "reason": "x"'
    path = tmp_path / "torn.jsonl"
    path.write_text(good + "\n" + torn, encoding="utf-8")
    lines = list(iter_session_log_lines(path))
    assert len(lines) == 1
    events = load_session_events(path, session_id="s1")
    assert len(events) == 1
    assert events[0].type == "turn.started.v1"
