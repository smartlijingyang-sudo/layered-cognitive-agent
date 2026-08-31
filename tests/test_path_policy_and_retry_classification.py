"""Tests for the host-fs path-policy seam and OSError retry classification.

Covers three orthogonal fixes (one assertion per seam):

1. ``lca.infrastructure.path_policy.validate_writable_file`` classifies
   empty strings, whitespace, existing directories and unwritable parents
   with the right failure_kind.
2. ``_DETERMINISTIC_EXCEPTIONS`` in both safe_executor implementations
   contains the four filesystem-derived exception subclasses that should
   fail-fast instead of burning retry budget on a guaranteed-identical
   OSError.
3. :class:`lca.plugins.tools.file_write.FileWriteTool` routes its
   rejection paths through ``FAILURE_KIND_VALIDATION`` /
   ``FAILURE_KIND_EXECUTION`` so the executor stops retrying.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from lca.cognition.body import pipeline_safe_executor as pipeline_executor_module
from lca.cognition.body import safe_executor as safe_executor_module
from lca.contracts.atoms.semantic_keys import (
    FAILURE_KIND,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_VALIDATION,
)
from lca.infrastructure.path_policy import validate_writable_file
from lca.plugins.tools.file_write import FileWriteTool

# ────────────────────────────────────────────────────────────
# A. path_policy
# ────────────────────────────────────────────────────────────


def test_validate_writable_file_accepts_normal_path(tmp_path: Path) -> None:
    target = tmp_path / "src" / "plugin.py"
    decision = validate_writable_file(target)
    assert decision.accept is True
    assert decision.error == ""
    assert decision.failure_kind == ""
    assert target.parent.exists()


def test_validate_writable_file_rejects_empty_string() -> None:
    decision = validate_writable_file(Path(""))
    assert decision.accept is False
    assert decision.failure_kind == "validation"
    assert decision.error  # any non-empty reason


def test_validate_writable_file_rejects_whitespace_only() -> None:
    decision = validate_writable_file(Path("   "))
    assert decision.accept is False
    assert decision.failure_kind == "validation"


def test_validate_writable_file_rejects_existing_directory(tmp_path: Path) -> None:
    decision = validate_writable_file(tmp_path)
    assert decision.accept is False
    assert decision.failure_kind == "validation"
    assert "已存在的目录" in decision.error


def test_validate_writable_file_classifies_unwritable_parent_as_execution(
    tmp_path: Path,
) -> None:
    # Construct an unwritable parent: tmp_path is read-only at the process level
    # via chmod 0o555 (r-x for owner).  /mnt is conventionally the right shape
    # on developer hosts, but it's environment-dependent; using tmp_path here
    # keeps the test hermetic.
    ro_parent = tmp_path / "ro"
    ro_parent.mkdir()
    nested = ro_parent / "deeper" / "file.py"
    ro_parent.chmod(0o555)
    try:
        decision = validate_writable_file(nested)
    finally:
        ro_parent.chmod(0o755)
    assert decision.accept is False
    assert decision.failure_kind == "execution"
    assert "无法创建父目录" in decision.error


# ────────────────────────────────────────────────────────────
# B. _DETERMINISTIC_EXCEPTIONS taxonomy
# ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "exc_cls",
    [PermissionError, IsADirectoryError, FileExistsError, FileNotFoundError],
)
def test_safe_executor_classifies_deterministic_oserror(exc_cls: type[BaseException]) -> None:
    assert exc_cls in safe_executor_module._DETERMINISTIC_EXCEPTIONS


@pytest.mark.parametrize(
    "exc_cls",
    [PermissionError, IsADirectoryError, FileExistsError, FileNotFoundError],
)
def test_pipeline_safe_executor_classifies_deterministic_oserror(
    exc_cls: type[BaseException],
) -> None:
    assert exc_cls in pipeline_executor_module._DETERMINISTIC_EXCEPTIONS


def test_safe_executor_does_not_classify_bare_oserror_as_deterministic() -> None:
    # Transient subclasses (BlockingIOError, InterruptedError, ...) and
    # bare OSError must remain on the transient side so network / pipe
    # failures keep being retried.
    assert OSError not in safe_executor_module._DETERMINISTIC_EXCEPTIONS
    assert OSError not in pipeline_executor_module._DETERMINISTIC_EXCEPTIONS


# ────────────────────────────────────────────────────────────
# C. FileWriteTool — execute path
# ────────────────────────────────────────────────────────────


def _run(coro):  # type: ignore[no-untyped-def]
    """Run a coroutine on a fresh event loop for hermetic test isolation."""
    return asyncio.new_event_loop().run_until_complete(coro)


def test_file_write_rejects_directory_path(tmp_path: Path) -> None:
    tool = FileWriteTool()
    obs = _run(tool.execute({"path": str(tmp_path), "content": "x", "mkdir_parents": True}))
    assert obs.success is False
    assert obs.extra[FAILURE_KIND] == FAILURE_KIND_VALIDATION
    assert "已存在的目录" in (obs.error or "")


def test_file_write_rejects_unwritable_path_as_execution() -> None:
    # /mnt/ is root:root + read-only on most developer hosts; if it's
    # missing in some sandboxes, skip rather than silently passing.
    if Path("/mnt").exists() and not Path("/mnt").is_dir():
        pytest.skip("/mnt not a directory on this host")
    tool = FileWriteTool()
    obs = _run(
        tool.execute(
            {
                "path": "/mnt/data/some-file.py",
                "content": "x",
                "mkdir_parents": True,
            }
        )
    )
    assert obs.success is False
    assert obs.extra[FAILURE_KIND] == FAILURE_KIND_EXECUTION
    assert "无法创建父目录" in (obs.error or "") or "Permission" in (obs.error or "")


def test_file_write_writes_file_when_path_is_clean(tmp_path: Path) -> None:
    tool = FileWriteTool()
    target = tmp_path / "out" / "plugin.py"
    obs = _run(
        tool.execute(
            {
                "path": str(target),
                "content": "print('hello')\n",
                "mkdir_parents": True,
            }
        )
    )
    assert obs.success is True, obs.error
    assert target.read_text(encoding="utf-8") == "print('hello')\n"


def test_file_write_validate_rejects_non_string_path() -> None:
    tool = FileWriteTool()
    err = tool.validate({"path": None, "content": "x"})
    assert err is not None
    assert "path" in err
