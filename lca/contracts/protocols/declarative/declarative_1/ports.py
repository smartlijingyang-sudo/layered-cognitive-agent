"""Port name closed set — typed contract for node-level data flow.

Per ADR-0219 §5: every port name written or read by a subgraph node must
appear here. Names not in this set are forbidden at the ``PortRegistry``
boundary (typed entry) and grep-rejected at runtime.

D5 mapping (each port name has one or more D4 consumers):

- ``decision``              think.classify / think.gate  →  outer interpreter / act phase
- ``observation``           observation nodes           →  outer interpreter
- ``reflection``            reflect nodes               →  outer interpreter
- ``response``              think.reason.complete       →  think.classify
- ``turn_plan``             think.reason.plan           →  think.reason.render
- ``turn_render``           think.reason.render         →  think.reason.complete
- ``in_assembled_manifest`` think.shortcut / think.route →  outer loop
- ``route_choice``          think.route                 →  downstream
- ``enforced_state``        think.route                 →  Reducer / state fold

Historical (deleted, no D4 consumer — see ADR-0219 §7.2):

- ``enforced_decision``     retired 2026-09-10 (was think.gate invented field)
- ``think_signal``          retired 2026-09-10 (was think.gate invented field)

Adding a new port name requires updating the D5 mapping table in
``docs/adr/0219-phase-graph-unification.md`` §5.1 alongside the code.
"""

from __future__ import annotations

from typing import Literal

PortName = Literal[
    "decision",
    "observation",
    "reflection",
    "response",
    "turn_plan",
    "turn_render",
    "in_assembled_manifest",
    "route_choice",
    "enforced_state",
]

__all__ = ["PortName"]
