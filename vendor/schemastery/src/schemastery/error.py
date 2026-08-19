"""Validation errors raised by the schemastery DSL.

Mirrors `~/deepseek-harness/vendor/schemastery/src/index.ts::ValidationError` —
a ``TypeError`` subclass carrying the path segments that led to the failure
so the message can be prefixed with a JSON-pointer-ish location (e.g.
``$.foo[1]``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Issue:
    """A single error record (used by the ``~standard`` adapter)."""

    message: str
    path: list[Any] = field(default_factory=list)


@dataclass
class Options:
    """Runtime validation options shared by every schema call.

    Mirrors the TS ``Schemastery.Options`` interface.
    """

    path: list[Any] = field(default_factory=list)
    autofix: bool = False
    ignore: Any = None  # callable ``(data, schema) -> bool`` or ``None``

    def copy(self) -> Options:
        return Options(path=list(self.path), autofix=self.autofix, ignore=self.ignore)

    def extend(self, key: Any) -> Options:
        return Options(path=[*self.path, key], autofix=self.autofix, ignore=self.ignore)


_VALIDATION_ERROR_MARKER = "__schemastery_validation_error__"


def format_path(path: Iterable[Any]) -> str:
    """Format a path list into the schemastery canonical string form.

    The TS source uses ``$`` as the root marker, ``.key`` for string
    segments, ``[i]`` for integer indices, and ``[Symbol(...)]`` for symbol
    segments. Python only has ``str`` / ``int`` segments in practice, but
    the symbol branch is kept for parity.
    """
    prefix = "$"
    for segment in path:
        if isinstance(segment, str):
            prefix += "." + segment
        elif isinstance(segment, int):
            prefix += f"[{segment}]"
        elif hasattr(segment, "name"):
            prefix += f"[Symbol({segment.name})]"
        else:  # pragma: no cover - defensive
            prefix += f"[{segment!r}]"
    if prefix.startswith("$."):
        prefix = "$" + prefix[2:]
    return prefix


class ValidationError(TypeError):
    """Raised by every ``Schema`` resolver when validation fails.

    The ``options`` field carries the path / autofix / ignore flag that
    was active at the failure site, mirroring TS exactly.
    """

    name: str = "ValidationError"

    def __init__(self, message: str, options: Options | None = None) -> None:
        opts = options or Options()
        path = format_path(opts.path)
        prefix = "" if path == "$" else f"{path} "
        super().__init__(f"{prefix}{message}")
        self.options = opts
        setattr(self, _VALIDATION_ERROR_MARKER, True)

    @staticmethod
    def is_(error: Any) -> bool:
        """Return ``True`` when ``error`` carries the schemastery marker.

        Renamed from the TS ``is`` because ``is`` is a Python keyword.
        """
        return bool(error is not None and getattr(error, _VALIDATION_ERROR_MARKER, False))
