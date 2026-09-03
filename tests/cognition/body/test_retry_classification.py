"""R1 regression: ``_DETERMINISTIC_EXCEPTIONS`` is shared across SafeExecutor implementations.

Both ``SimpleSafeExecutor`` and ``PipelineSafeExecutor`` historically
maintained their own copy of the tuple — literal duplicates with the
same long comment about ``/mnt/data-style inputs``.  R1 consolidates
the tuple into ``lca/cognition/body/_retry_classification.py`` so the
two implementations cannot drift.

This test drives the real shipped constant and the two executors that
consume it.  It also asserts the structural fact that both executors
share the same identity (object identity), so a future tool-runtime
incident can be added once.
"""

from __future__ import annotations

from lca.cognition.body import pipeline_safe_executor as _pipeline_mod
from lca.cognition.body import safe_executor as _safe_mod
from lca.cognition.body._retry_classification import _DETERMINISTIC_EXCEPTIONS


def test_deterministic_exceptions_contains_value_error() -> None:
    """The shared tuple classifies ValueError as non-retryable."""
    assert ValueError in _DETERMINISTIC_EXCEPTIONS


def test_deterministic_exceptions_contains_os_deterministic_subtypes() -> None:
    """The ``/mnt/data-style inputs`` incident motivated these OSError subtypes."""
    for cls in (
        PermissionError,
        IsADirectoryError,
        FileExistsError,
        FileNotFoundError,
    ):
        assert cls in _DETERMINISTIC_EXCEPTIONS, f"{cls.__name__} must be non-retryable"


def test_deterministic_exceptions_excludes_bare_oserror() -> None:
    """Bare ``OSError`` is intentionally left OUT so transient subclasses retry."""
    assert OSError not in _DETERMINISTIC_EXCEPTIONS


def test_safe_executor_imports_shared_constant() -> None:
    """SimpleSafeExecutor must re-use the shared tuple (not its own copy)."""
    assert _safe_mod._DETERMINISTIC_EXCEPTIONS is _DETERMINISTIC_EXCEPTIONS


def test_pipeline_executor_imports_shared_constant() -> None:
    """PipelineSafeExecutor must re-use the same shared tuple (not its own copy)."""
    assert _pipeline_mod._DETERMINISTIC_EXCEPTIONS is _DETERMINISTIC_EXCEPTIONS


def test_both_executors_share_one_tuple() -> None:
    """Both executors consume the SAME tuple (object identity)."""
    assert _safe_mod._DETERMINISTIC_EXCEPTIONS is _pipeline_mod._DETERMINISTIC_EXCEPTIONS


def test_deterministic_exceptions_tuple_is_hashable() -> None:
    """Tuple of exception types must be hashable for memoization / set membership."""
    # If this fails the test indicates a regression where a non-type was added.
    hash(_DETERMINISTIC_EXCEPTIONS)
