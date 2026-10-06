from __future__ import annotations

# ADR-0281 T3: run-artifact writer discipline scan (owner-only bound).
import os
import stat
from pathlib import Path

import pytest

from lca.infrastructure.observability.journal.backends.filesystem import (
    FilesystemJournalStore,
)
from lca.infrastructure.observability.writable_matrix import RoutingFileStorage
from lca.infrastructure.persistence.run_paths import RUN_DIR_MODE

# Every writer that creates run artifacts must hold the owner-only bound:
#
# - C1 (directory): per-run directory creation must go through
#   ``ensure_run_dir`` (0700, tightened on every call);
# - C2 (file): artifact files must be created with ``RUN_ARTIFACT_MODE``
#   (0600) passed to ``os.open`` -- umask can only tighten, never loosen;
# - T1 (directory-bound cover): a writer that states no file mode at all is
#   covered by the directory bound, provided the directory itself went
#   through ``ensure_run_dir``.
#
# This module pins the writer registry so a new writer that adds a bare
# ``mkdir``/``open`` on run artifacts turns the scan red instead of silently
# breaking the contract. The two former C1 deviations
# (``writable_matrix/defaults.py``, ``journal/backends/filesystem.py``) were
# routed through ``ensure_run_dir`` by the quality lane (2026-10-04); their
# regression tests are plain behavior tests now. A new known deviation is
# pinned by mapping the file to None in ``_BARE_MKDIR_ALLOWLIST`` below plus
# a regression test asserting the 0700 bound.
#
# NOTE: the contract text lives in comments, not the module docstring,
# because ruff 0.15.14 misfires E402 on multi-line docstrings placed before
# imports.

REPO_ROOT = Path(__file__).resolve().parents[4]
LCA = REPO_ROOT / "lca"

assert LCA.is_dir(), f"T3 scan: repo layout changed, {LCA} is not a directory"

# Writers that own per-run directory creation (ADR-0281 C1). Each must
# reference ``ensure_run_dir`` from ``lca.infrastructure.persistence.run_paths``.
_DIR_WRITERS = [
    "infrastructure/observability/spine/sinks/file_sink.py",
    "infrastructure/persistence/run_buffer_registry.py",
    "plugins/observability/run/ledger_seam.py",
    "plugins/transport/webserver/handlers/runs/terminal/failure.py",
]

# Every writer scanned for bare mkdir/open, with the expected discipline.
_SCANNED_WRITERS = [
    *_DIR_WRITERS,
    "infrastructure/observability/writable_matrix/defaults.py",
    "infrastructure/observability/journal/backends/filesystem.py",
    "infrastructure/persistence/jsonl_sink.py",
    "infrastructure/observability/journal/step/narrative_writer/writer.py",
]


def _source(rel: str) -> str:
    path = LCA / rel
    assert path.exists(), f"T3 registry stale: writer moved without updating this file: {rel}"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", _DIR_WRITERS)
def test_per_run_dir_writers_route_through_ensure_run_dir(rel: str) -> None:
    """ADR-0281 C1: per-run directory creation must go through ``ensure_run_dir``."""
    assert "ensure_run_dir" in _source(rel), (
        f"{rel} no longer references ensure_run_dir -- per-run dirs would be "
        "created umask-dependent (ADR-0281 C1)"
    )


@pytest.mark.parametrize("rel", _SCANNED_WRITERS)
def test_os_open_calls_state_run_artifact_mode(rel: str) -> None:
    """ADR-0281 C2: any ``os.open`` in a run-artifact writer must pass ``RUN_ARTIFACT_MODE``."""
    src = _source(rel)
    if "os.open(" not in src:
        pytest.skip(f"{rel} has no os.open call")
    assert "RUN_ARTIFACT_MODE" in src, (
        f"{rel} calls os.open without RUN_ARTIFACT_MODE -- artifact files would be "
        "created umask-dependent (ADR-0281 C2)"
    )


def _bare_mkdir_hits() -> list[str]:
    hits: list[str] = []
    for rel in _SCANNED_WRITERS:
        for lineno, line in enumerate(_source(rel).splitlines(), 1):
            stripped = line.strip()
            if ".mkdir(" in stripped and "ensure_run_dir" not in stripped:
                hits.append(f"{rel}:{lineno}: {stripped}")
    return hits


# Bare ``mkdir`` calls that are NOT per-run-dir violations, each with the
# reason it is allowed. A file mapped to None is a KNOWN DEVIATION
# (ADR-0281 C1 gap) pinned by a regression test below (none currently);
# fixing a deviation requires removing the file from this map AND turning
# its regression test into a plain behavior test.
_BARE_MKDIR_ALLOWLIST = {
    "plugins/observability/run/ledger_seam.py": (
        "root.mkdir(parents=True, exist_ok=True)",
        "factory runs-root (traces/runs), not a per-run dir",
    ),
    "infrastructure/persistence/jsonl_sink.py": (
        "self._path.parent.mkdir(parents=True, exist_ok=True)",
        "standalone fallback; production callers ensure_run_dir first",
    ),
    "infrastructure/observability/journal/step/narrative_writer/writer.py": (
        "self._path.parent.mkdir(parents=True, exist_ok=True)",
        "covered by ensure-first ordering in create_run_components",
    ),
}


def test_no_unlisted_bare_mkdir_on_run_artifact_writers() -> None:
    """Every bare ``mkdir`` in a scanned writer must be an allowlisted non-violation."""
    unexpected = []
    for hit in _bare_mkdir_hits():
        rel = hit.split(":", 1)[0]
        allow = _BARE_MKDIR_ALLOWLIST.get(rel)
        if allow is None:
            unexpected.append(hit)
            continue
        fragment, _reason = allow
        if fragment not in hit:
            unexpected.append(hit + f"  <-- allowlisted fragment changed: {fragment!r}")
    assert not unexpected, "new bare mkdir on run-artifact writers (ADR-0281 C1):\n" + "\n".join(
        unexpected
    )


def test_narrative_writer_mkdir_covered_by_ensure_first() -> None:
    """The narrative writer's bare mkdir is harmless only because
    ``create_run_components`` calls ``ensure_run_dir`` first -- pin the ordering."""
    src = _source("plugins/observability/run/ledger_seam.py")
    body = src.split("def create_run_components", 1)[1]
    assert body.index("ensure_run_dir(spine_path.parent)") < body.index("StepNarrativeWriter("), (
        "ensure_run_dir must precede StepNarrativeWriter construction in create_run_components"
    )


def test_routing_file_storage_holds_dir_bound_on_first_write(tmp_path: Path) -> None:
    """ADR-0281 C1: as the first writer, the storage holds the run dir at 0700."""
    prev = os.umask(0o022)
    try:
        run_dir = tmp_path / "run_first_writer"
        storage = RoutingFileStorage(run_dir, spine_filename=True)
        try:
            storage.write(b"{}\n")
        finally:
            storage.close()
    finally:
        os.umask(prev)
    assert stat.S_IMODE(run_dir.stat().st_mode) == RUN_DIR_MODE


def test_filesystem_journal_store_holds_dir_bound(tmp_path: Path) -> None:
    """ADR-0281 C1: as the first writer, the journal store holds the run dir at 0700."""
    prev = os.umask(0o022)
    try:
        run_dir = tmp_path / "run_journal_first"
        store = FilesystemJournalStore(run_dir)
        try:
            pass
        finally:
            store.close()
    finally:
        os.umask(prev)
    assert stat.S_IMODE(run_dir.stat().st_mode) == RUN_DIR_MODE
