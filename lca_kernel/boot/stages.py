"""Stage SSOT — the unique authoritative definition of boot phases.

Why a dedicated module
----------------------
Stage vocabulary used to be defined independently in four files (the original
ADR-0111/0113/0114 set). BootJournalEvent.stage, lca-ops --scope boot
filtering, and the BootTrace snapshot all need to agree on the same numeric
identifiers. This :class:`IntEnum` is that single source of truth; any new
phase requires an ADR (ADR-0115 §决定 1 C1).

Public surface
--------------
- :class:`Stage` — IntEnum, source = 1, monotonic, six entries.
"""

from __future__ import annotations

from enum import IntEnum


class Stage(IntEnum):
    """Boot phase identifiers; values start at 1.

    The offset from zero keeps these distinct from the journal ``seq``
    counter, which starts at 0, and from line/file offsets reported by
    trace tools. Adding a new entry must be paired with an ADR (ADR-0115
    §决定 1 C1: closure discipline).
    """

    SOURCE = 1  # K1 input adapter
    RESOLVE = 2  # K1 domain validation
    TOPO = 3  # K1 DAG topology
    PLAN = 4  # K2 plan compilation
    BOOT = 5  # K3 cordis Context + Fiber spawn
    OBSERVABILITY = 6  # K5 BoundObservability assembly


__all__ = ["Stage"]
