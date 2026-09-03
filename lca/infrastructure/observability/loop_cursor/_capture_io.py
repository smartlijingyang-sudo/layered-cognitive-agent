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

import hashlib
import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any

from lca.contracts.observability.ssot import to_jsonable

_log = logging.getLogger(__name__)

_DIGEST_PREFIX = "sha256:"
"""Digest string prefix; matches step_tree_accumulator and other model-visible writers."""


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
