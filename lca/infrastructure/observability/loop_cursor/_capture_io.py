"""Shared I/O helpers for model-visible captures (ADR-0169 D7 + ADR-0175 D1).

Private module. Both :class:`StdModelVisibleCapture` and
:class:`StdReasonerPromptCapture` use the same 4 helpers:

- :func:`to_jsonable` — best-effort arbitrary → JSON-compatible conversion.
- :func:`sha256_digest` — stable digest in ``sha256:<hex>`` form.
- :func:`relative_posix` — POSIX-style relative path with graceful fallback.
- :func:`write_json` — mkdir-parents + write + return digest.

Moving the helpers here removes the duplication between the two capture
modules and gives a single seam for "where do model-visible writes go".

The ``sha256`` digest format is the cross-component contract — any reader
must accept ``sha256:<hex>`` and may reject other forms.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any

_log = logging.getLogger(__name__)

_DIGEST_PREFIX = "sha256:"
"""Digest string prefix; matches step_tree_accumulator and other model-visible writers."""


def to_jsonable(value: Any) -> Any:
    """Convert arbitrary objects to JSON-compatible structures.

    Priority:
      1. Already JSON-compatible primitives / containers -> as-is.
      2. ``dataclasses`` instance -> ``dataclasses.asdict`` (covers frozen + slots).
      3. ``to_dict`` / ``model_dump`` / ``dict()`` -> call.
      4. ``__dict__`` -> take it.
      5. ``repr(value)`` as final fallback.

    Guarantees ``json.dumps(...)`` does not raise TypeError.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return to_jsonable(dataclasses.asdict(value))
        except Exception as exc:
            _log.debug("capture_io asdict failed: %s", exc)
    for proto_name in ("to_dict", "model_dump", "dict"):
        proto = getattr(value, proto_name, None)
        if callable(proto):
            try:
                return to_jsonable(proto())
            except Exception as exc:
                _log.debug("capture_io %s() failed: %s", proto_name, exc)
    if hasattr(value, "__dict__"):
        try:
            return to_jsonable(vars(value))
        except Exception as exc:
            _log.debug("capture_io vars() failed: %s", exc)
    return repr(value)


def sha256_digest(payload: Any) -> str:
    """Stable ``sha256:<hex>`` digest for a JSON-serialisable payload."""
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def relative_posix(run_dir: Path, target: Path) -> str:
    """POSIX-style relpath; fallback to basename on cross-device errors.

    Never raises — captures must never lose the cursor's
    record_request_header path because of path arithmetic.
    """
    try:
        rel = target.relative_to(run_dir)
    except ValueError:
        return target.name
    return PurePosixPath(rel.as_posix()).as_posix()


def write_json(path: Path, payload: Any) -> str:
    """mkdir parents + write JSON + return sha256 digest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    jsonable = to_jsonable(payload)
    serialized = json.dumps(
        jsonable,
        ensure_ascii=False,
        indent=2,
        default=str,
        sort_keys=False,
    )
    path.write_text(serialized, encoding="utf-8")
    return sha256_digest(jsonable)


__all__ = [
    "relative_posix",
    "sha256_digest",
    "to_jsonable",
    "write_json",
]
