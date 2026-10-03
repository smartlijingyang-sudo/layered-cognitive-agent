"""Append-stream run artifacts must not be group or other readable.

Two writers open their own fd for a per-run append stream: ``FileSink`` for
``<run_id>.spine.jsonl`` plus ``<run_id>.exceptions.jsonl``, and
``RoutingFileStorage`` for the same ledger name on the writable-matrix face.
The derived artifacts beside them (``journal.json``, ``journal.narrative.md``,
``manifest.json``) come out 0600 because ``atomic_write_text`` creates them
through ``tempfile``. The append streams carry strictly more: the spine holds
full tool payloads and full prompt text, so whatever a tool downloads lands
there verbatim. ``run_56c3352cd22e`` parsed a Google Sheets password list and
its plaintext credentials appeared 22 times in that run's ``.spine.jsonl``.

The assertion is the absence of group and other bits rather than an exact
mode, because ``os.open`` ANDs the requested mode with the process umask. The
property that matters is that no one but the owner can read; the exact owner
bits may legitimately be stricter than requested.

The directory bound is the mechanism that actually covers the run, because
the artifacts reach it through several independent writers and the
write-behind ``JsonlFileSink`` states no mode of its own. The file-level
assertions stay because two writers requested group read explicitly, and that
request should not come back.
"""

from __future__ import annotations

import stat
from datetime import UTC, datetime
from pathlib import Path

from lca.infrastructure.observability.spine.event.record import EventRecord
from lca.infrastructure.observability.spine.sinks.file_sink import FileSink
from lca.infrastructure.observability.writable_matrix import RoutingFileStorage
from lca.infrastructure.persistence.run_paths import RUN_DIR_MODE, ensure_run_dir

GROUP_OR_OTHER_BITS = 0o077


def _record() -> EventRecord:
    return EventRecord(
        execution_point="think.gate.start",
        channel="fact",
        span_id="01HM",
        parent_span_id=None,
        sequence=1,
        epoch=1,
        causality_id="ca",
        outcome=None,
        when=datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC),
        when_corrected=datetime(2026, 10, 4, 12, 0, 0, 100000, tzinfo=UTC),
        prev_event_hash=None,
        run_id="run_mode",
        step_id="s1",
        payload={"x": 1},
    )


def _assert_owner_only(path: Path) -> None:
    assert path.exists(), f"{path.name} was not created"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode & GROUP_OR_OTHER_BITS == 0, f"{path.name} is group/other accessible: {oct(mode)}"


def test_file_sink_ledger_and_exceptions_index_are_owner_only(tmp_path: Path) -> None:
    """Both fds ``FileSink`` opens land owner-only, including the empty index.

    The modes are read before ``close()`` because a run with zero exceptions
    unlinks its placeholder index on close.
    """
    sink = FileSink(tmp_path, run_id="run_mode")
    try:
        sink.write(_record())
        _assert_owner_only(tmp_path / "run_mode.spine.jsonl")
        _assert_owner_only(tmp_path / "run_mode.exceptions.jsonl")
    finally:
        sink.close()


def test_routing_file_storage_ledger_is_owner_only(tmp_path: Path) -> None:
    """The writable-matrix storage face states the same bound for the same name."""
    run_dir = tmp_path / "run_mode"
    storage = RoutingFileStorage(run_dir, spine_filename=True)
    storage.write(b"{}\n")
    storage.close()

    _assert_owner_only(run_dir / "run_mode.spine.jsonl")


def test_ensure_run_dir_holds_the_access_bound(tmp_path: Path) -> None:
    """The directory bound is what covers writers that state no mode at all."""
    run_dir = ensure_run_dir(tmp_path / "run_mode")

    assert stat.S_IMODE(run_dir.stat().st_mode) == RUN_DIR_MODE


def test_ensure_run_dir_tightens_a_directory_that_already_exists(tmp_path: Path) -> None:
    """Any writer arriving second still tightens the directory.

    ``mkdir(exist_ok=True)`` leaves an existing directory at whatever mode it
    already had, so whichever writer creates the run directory first would
    otherwise decide the bound for every artifact written after it.
    """
    run_dir = tmp_path / "run_mode"
    run_dir.mkdir()
    run_dir.chmod(0o775)

    ensure_run_dir(run_dir)

    assert stat.S_IMODE(run_dir.stat().st_mode) == RUN_DIR_MODE


def test_file_sink_tightens_the_run_directory_it_writes_into(tmp_path: Path) -> None:
    """The live sink enforces the bound on the directory, not just its own fd."""
    run_dir = tmp_path / "run_mode"
    run_dir.mkdir()
    run_dir.chmod(0o775)

    sink = FileSink(run_dir, run_id="run_mode")
    try:
        sink.write(_record())
    finally:
        sink.close()

    assert stat.S_IMODE(run_dir.stat().st_mode) == RUN_DIR_MODE
