"""Standing-file polls stay quiet until a later edit."""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.adapters.polling import (
    poll_standing_home,
    reset_standing_cursors,
)
from lca.infrastructure.memory.contextfiles.events.publisher import (
    InProcessEventPublisher,
    StandingChanged,
)
from lca.infrastructure.memory.contextfiles.ports.file_store import FileStore
from lca.infrastructure.memory.contextfiles.service.watch import StandingCursor


class _FlakyStore:
    """Fails the next ``USER.md`` read once, then delegates."""

    def __init__(self, inner: FileStore) -> None:
        self._inner = inner
        self._failed = False

    def read_text(self, relative_path: str) -> str:
        if relative_path == "USER.md" and not self._failed:
            self._failed = True
            raise OSError("busy")
        return self._inner.read_text(relative_path)


def test_first_poll_is_silent_and_second_poll_reports_the_edit(tmp_path: Path) -> None:
    memory = tmp_path / "MEMORY.md"
    memory.write_text("用户住在上海\n", encoding="utf-8")
    publisher = InProcessEventPublisher()
    events: list[object] = []
    publisher.subscribe(events.append)
    cursor = StandingCursor(publisher)
    store = DiskFileStore(tmp_path)
    assert cursor.poll(store) == ""
    memory.write_text("用户住在杭州\n", encoding="utf-8")
    note = cursor.poll(store)
    assert "常驻文件有更新" in note
    assert "用户住在上海" in note
    assert "用户住在杭州" in note
    assert len(events) == 1
    assert isinstance(events[0], StandingChanged)
    assert events[0].path == "MEMORY.md"
    assert cursor.poll(store) == ""


def test_read_failure_does_not_report_a_deletion(tmp_path: Path) -> None:
    (tmp_path / "USER.md").write_text("不要啰嗦\n", encoding="utf-8")
    cursor = StandingCursor()
    store = DiskFileStore(tmp_path)
    assert cursor.poll(store) == ""
    flaky = _FlakyStore(store)
    assert cursor.poll(flaky) == ""


def test_poll_standing_home_uses_one_cursor_per_home(tmp_path: Path) -> None:
    reset_standing_cursors()
    (tmp_path / "SOUL.md").write_text("旧人设\n", encoding="utf-8")
    assert poll_standing_home(str(tmp_path)) == ""
    (tmp_path / "SOUL.md").write_text("新人设\n", encoding="utf-8")
    note = poll_standing_home(str(tmp_path))
    assert "新人设" in note
    reset_standing_cursors()
