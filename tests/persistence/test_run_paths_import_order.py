"""``run_paths`` must stay importable before the spine sinks package.

``run_paths`` resolves artifact names through ``spine.sinks.naming``, and
importing that package executes ``spine/sinks/__init__.py``, which imports
``FileSink``. ``FileSink`` needs ``ensure_run_dir`` from ``run_paths``. A
module-level naming import in ``run_paths`` therefore resolves the module
while it is still initializing, and the CLI dies at import time with
``ImportError: cannot import name 'ensure_run_dir' from partially initialized
module``.

The pytest suite does not catch this because collection imports the sinks
package first. ``lca-ops`` imports in the opposite order and breaks. Each
order gets a fresh interpreter here so the check does not depend on what an
earlier test in the same process already imported.
"""

from __future__ import annotations

import subprocess
import sys

RUN_PATHS = "lca.infrastructure.persistence.run_paths"
FILE_SINK = "lca.infrastructure.observability.spine.sinks.file_sink"
JOURNAL_BACKENDS = "lca.infrastructure.observability.journal.backends.filesystem"

_BOOTSTRAP = (
    "import {first}, {second};"
    "import lca.infrastructure.persistence.run_buffer_registry;"
    "p = lca.infrastructure.persistence.run_paths;"
    "assert str(p.spine_path_for_run('run_x')).endswith('run_x/run_x.spine.jsonl');"
    "assert str(p.exceptions_path_for_run('run_x')).endswith('run_x/run_x.exceptions.jsonl');"
    "assert oct(p.RUN_DIR_MODE) == '0o700';"
    "print('ok')"
)


def _import_pair(first: str, second: str) -> str:
    result = subprocess.run(  # noqa: S603 - executable and module names are fixed literals
        [sys.executable, "-c", _BOOTSTRAP.format(first=first, second=second)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"importing {first} before {second} failed:\n{result.stderr[-2000:]}"
    )
    return result.stdout.strip()


def test_run_paths_imports_before_the_spine_sinks() -> None:
    """The order ``lca-ops`` uses: run_paths resolves first."""
    assert _import_pair(RUN_PATHS, FILE_SINK) == "ok"


def test_spine_sinks_import_before_run_paths() -> None:
    """The order pytest collection happens to use."""
    assert _import_pair(FILE_SINK, RUN_PATHS) == "ok"


def test_journal_backends_still_resolve_through_persistence() -> None:
    """The CLI's own import chain, which is what surfaced the cycle."""
    result = subprocess.run(  # noqa: S603 - executable and module name are fixed literals
        [sys.executable, "-c", f"import {JOURNAL_BACKENDS}; print('ok')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"journal backends import failed:\n{result.stderr[-2000:]}"
    assert result.stdout.strip() == "ok"
