"""GateDecided / PolicyFact — closed-loop decision gate observability (v3 §3.5).

A DecisionGate MAY rewrite a Decision.  When it does, the rewrite must be
recorded as a ``GateDecided`` event so the journal carries the full
provenance.  When a gate emits a *warning* (e.g. ``RepeatToolCallGate``),
it does not rewrite the decision but still emits a ``GateDecided`` event
with a ``PolicyFact`` attached.  The next ``ContextManifest`` automatically
folds the PolicyFact into the LLM context — the Reasoner never reads the
gate's working_memory slot directly.

This module is the contract layer.  The journal dataclass is intentionally
repeated here (rather than re-exporting from ``observability.journal``) so
that the L1 gate layer can import it without crossing to the observability
package — keeping the import graph one-way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PolicyFact:
    """A single fact emitted by a DecisionGate.

    - ``kind``: stable string identifier (e.g. ``repeat_tool_call``)
    - ``message``: human-readable text the Reasoner eventually sees
    - ``source``: gate name (e.g. ``RepeatToolCallGate``)
    - ``extra``: opaque payload for downstream tooling
    """

    kind: str
    message: str
    source: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GateDecided:
    """Single gate's verdict for the current think step.

    The verdict is one of: ``allow`` | ``warn`` | ``deny`` | ``rewrite``.
    ``allow`` is the default and intentionally NOT recorded (the spec says
    "allow 默认不记"), so the helper only fires for the other three.
    """

    event_id: str
    gate: str
    verdict: str
    is_rewritten: bool
    policy_fact: PolicyFact | None = None
    tool_name: str | None = None
    rationale: str | None = None
