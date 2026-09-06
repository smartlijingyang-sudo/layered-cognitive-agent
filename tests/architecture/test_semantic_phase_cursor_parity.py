"""ADR-0194 §7 L3: SemanticPhase must match LoopCursor phase fold set."""

from __future__ import annotations

import typing

from lca.contracts.protocols.declarative.declarative_1.declarative_common import SemanticPhase


def test_semantic_phase_matches_loop_cursor_phase_names() -> None:
    from lca.contracts.observability.cursor.loop_cursor import PhaseName

    semantic = frozenset(phase.value for phase in SemanticPhase)
    cursor = frozenset(typing.get_args(PhaseName))
    assert semantic == cursor, f"SemanticPhase {semantic} != PhaseName {cursor}"
