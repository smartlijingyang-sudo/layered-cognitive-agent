"""Per-run durable artifact path helpers (ADR-0169 / ADR-0186).

Session persistence observers derive ``run_id`` from the Session delivery
shape ``"{session.id}:{seq}"`` and resolve spine / exceptions paths under
``traces/runs/<run_id>/`` unless a test override ``run_dir`` is supplied.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

_RUNS_ROOT_ENV = "LCA_RUNS_ROOT"
_DEFAULT_RUNS_ROOT = Path("traces") / "runs"


def default_runs_root() -> Path:
    """Resolve the runs root: ``LCA_RUNS_ROOT`` when set, else ``traces/runs``.

    The test suite sets ``LCA_RUNS_ROOT`` session-wide so profile-driven
    sinks write into a temporary directory instead of the production tree.
    The kernel launcher leaves it unset and keeps the on-disk default.
    """
    override = os.environ.get(_RUNS_ROOT_ENV)
    if override:
        return Path(override)
    return _DEFAULT_RUNS_ROOT


RUN_DIR_MODE = 0o700
"""Access bound for ``traces/runs/<run_id>/``.

Everything a run writes there is model or tool content: the spine ledger
carries full prompt text and full tool payloads, so whatever a tool downloads
lands in it verbatim. ``run_56c3352cd22e`` parsed a Google Sheets password
list and the plaintext credentials appeared 22 times in its ``.spine.jsonl``.

The bound sits on the directory because the artifacts reach it through
several independent writers (write-behind ``JsonlFileSink``, ``FileSink``,
``RoutingFileStorage``, the kernel ``SpineSink``) and more can be added.
``mkdir`` alone is not enough: its mode is ANDed with the process umask and
``exist_ok=True`` leaves an existing directory untouched, so this chmods
unconditionally and stays idempotent. ``traces/`` is not mounted into the
sandbox and no other user reads it.
"""


def ensure_run_dir(path: Path) -> Path:
    """Create ``path`` if needed and hold it at :data:`RUN_DIR_MODE`.

    precondition: ``path`` is a per-run directory under the runs root, or a
    test override standing in for one.
    失败语义: ``mkdir`` 失败原样上抛; ``chmod`` 失败被抑制, 因为目录已存在时
    它可能属于别的 owner, 而那不该让 run 落盘失败。
    时序: mkdir → chmod, 每次调用都 chmod, 所以任何一个 writer 先到都会把
    已存在的目录收紧。
    """
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(RUN_DIR_MODE)
    return path


def run_id_from_event_id(event_id: str) -> str:
    """Parse ``run_id`` from ``"{session.id}:{seq}"`` delivery shape."""
    run_id, sep, seq = event_id.rpartition(":")
    if not sep or not run_id or not seq.isdigit():
        raise ValueError(
            f"无法从 event_id={event_id!r} 推导 run_id（Session 投递契约 '{{session.id}}:{{seq}}'）"
        )
    return run_id


def run_dir_for(run_id: str, *, run_dir: Path | None = None) -> Path:
    """Resolve the per-run directory (creates nothing)."""
    if run_dir is not None:
        return run_dir
    return default_runs_root() / run_id


def spine_path_for_run(run_id: str, *, run_dir: Path | None = None) -> Path:
    """``<run_dir>/<run_id>.spine.jsonl`` durable ledger path."""
    # Deferred: ``spine.sinks.__init__`` pulls in ``FileSink``, which imports
    # ``ensure_run_dir`` from here. A module-level import would make this
    # module resolve while it is still initializing.
    from lca.infrastructure.observability.spine.sinks.naming import spine_filename_for_run

    return run_dir_for(run_id, run_dir=run_dir) / spine_filename_for_run(run_id)


def exceptions_path_for_run(run_id: str, *, run_dir: Path | None = None) -> Path:
    """``<run_dir>/<run_id>.exceptions.jsonl`` grep-friendly index path."""
    from lca.infrastructure.observability.spine.sinks.naming import (
        exceptions_filename_for_run,
    )

    return run_dir_for(run_id, run_dir=run_dir) / exceptions_filename_for_run(run_id)


__all__ = [
    "RUN_DIR_MODE",
    "default_runs_root",
    "ensure_run_dir",
    "exceptions_path_for_run",
    "run_dir_for",
    "run_id_from_event_id",
    "spine_path_for_run",
]
