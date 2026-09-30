"""Span opener port (telemetry seam for harness phase observers).

Harness must depend only on contracts. The concrete OpenTelemetry-backed
``span`` function lives in infrastructure; this protocol lets harness callers
inject a span factory from the composition boundary.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SpanOpener(Protocol):
    """Open a named telemetry span as a context manager."""

    def __call__(
        self,
        name: object,
        **attributes: Any,
    ) -> AbstractContextManager[object]: ...


__all__ = ["SpanOpener"]
