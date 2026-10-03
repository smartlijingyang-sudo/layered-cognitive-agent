"""Peer standing envelope: redacted standing snapshot for cross-trust-boundary delegates.

ADR-0257 §7 (decided 2026-10-01): a same-machine subagent inherits the full
standing snapshot (``assemble_standing``); a peer delegate — another machine or
organization, e.g. peter — only receives the redacted envelope, with PII
stripped and task-relevant context kept. ADR-0276 T8 nails the seam.

This module owns the peer side only. The same-machine path is untouched:
``assemble_standing`` keeps emitting verbatim bodies (see
``test_same_machine_keeps_pii_verbatim``).

Redaction strategy (mask, not delete): spans are replaced with
``[PII-REDACTED]`` so the reader still sees *that* contact/address information
exists, without seeing the value. Categories covered:

- phone numbers: Chinese mobile with optional +86 prefix;
- email addresses;
- Chinese addresses anchored on an administrative token (省/市/区/县 …)
  followed by a numeric component (门牌号 etc.).

Explicitly NOT covered: personal names, digit-less addresses, and credential
secrets (API keys, passwords, tokens). Names are identity context a delegate
usually needs; credentials belong to ``curated.contains_secret`` at projection
time — the T8 nail leaves the PII category list as an open design point
(whether to reuse the 0253/0266 credential red-line list). If a caller needs
span-level credential masking here, wire it through the curated pattern rather
than forking it.

Budget and skeleton semantics mirror ``assemble_standing``: redaction runs on
the raw bodies *before* packing, so budget fitting and truncation see
already-safe text, and the ``<!-- INJECTED FILE: <name> -->`` slots survive
untouched. The output carries the provenance marker ``standing_redacted``
(0258 C2) as its first line; the marker itself counts against the budget.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from lca.infrastructure.memory.contextfiles.domain.standing import assemble_standing

_MARKER = "<!-- standing_redacted: peer envelope; PII masked (ADR-0257 §7, ADR-0276 T8) -->"
_PLACEHOLDER = "[PII-REDACTED]"

_PHONE = re.compile(r"(?:\+?86[-\s]?)?1[3-9]\d{9}")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_ADDRESS = re.compile(
    r"[\u4e00-\u9fff]{1,24}"
    r"(?:省|市|自治区|自治州|区|县)"
    r"[\u4e00-\u9fff\d\s\-－—–·（）()]{0,24}"
    r"[\d一二三四五六七八九十百千]"
    r"(?:\s*[号栋单元室楼])?"
)


def redact_pii(text: str) -> str:
    """Mask phone numbers, email addresses and Chinese addresses in ``text``."""
    redacted = _PHONE.sub(_PLACEHOLDER, text)
    redacted = _EMAIL.sub(_PLACEHOLDER, redacted)
    return _ADDRESS.sub(_PLACEHOLDER, redacted)


def pack_peer_standing(
    files: Sequence[tuple[str, str]],
    *,
    budget_chars: int,
    order: Sequence[str] | None = None,
) -> str:
    """Pack a PII-redacted standing snapshot for a peer delegate.

    Same ``files``/``budget_chars``/``order`` contract as ``assemble_standing``;
    the returned text carries the ``standing_redacted`` provenance marker and
    must differ from the same-machine snapshot for the same input.
    """
    if budget_chars <= 0:
        return ""
    redacted = [(name, redact_pii(body)) for name, body in files]
    headroom = budget_chars - len(_MARKER) - 2
    if headroom <= 0:
        return _MARKER[:budget_chars]
    packed = assemble_standing(redacted, budget_chars=headroom, order=order)
    if not packed:
        return _MARKER
    return f"{_MARKER}\n\n{packed}"


__all__ = ["pack_peer_standing", "redact_pii"]
