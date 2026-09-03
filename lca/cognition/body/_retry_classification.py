"""Retry-classification constants for SafeExecutor implementations (R1).

The ``SimpleSafeExecutor`` and ``PipelineSafeExecutor`` historically each
defined their own copy of ``_DETERMINISTIC_EXCEPTIONS`` — and the comment
on either copy told the same story (the ``/mnt/data-style inputs`` incident
that motivated making these exceptions non-retryable).  Two copies drift
independently; R1 consolidates the tuple here.

Deletion test: yes, this concentrates complexity.  Both executors can
now share a single non-retryable-exception classifier.  Future tool-runtime
incidents only need to be added once.
"""

from __future__ import annotations

_DETERMINISTIC_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    SyntaxError,
    IndexError,
    NameError,
    NotImplementedError,
    OverflowError,
    ZeroDivisionError,
    # OS-level failures against a fixed (path, args) tuple never resolve by
    # retrying — re-running write_bytes() into the same directory produces the
    # same PermissionError.  Without this, /mnt/data-style inputs cause the
    # agent to burn through retry_policy.max_retries=3 + 1 = 4 attempts
    # before surfacing the obvious cause.  Bare OSError is intentionally left
    # out so transient subclasses (BlockingIOError / InterruptedError / etc.)
    # stay retryable.
    PermissionError,
    IsADirectoryError,
    FileExistsError,
    FileNotFoundError,
)

__all__ = ["_DETERMINISTIC_EXCEPTIONS"]
