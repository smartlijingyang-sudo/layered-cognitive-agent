"""Cognition-plane Decision — re-export of the canonical cross-graph DTO.

The frozen ``Decision`` dataclass lives at
:mod:`lca.contracts.models.core.execution.decision` (ADR-0220 §4.2 cross-
graph boundary). This module re-exports it under the cognition-namespace
import path so cognition-plane consumers (intervene / think / reflect
subgraphs) depend on a single canonical type via a single import line.
"""

from lca.contracts.models.core.execution.decision import (
    Decision as Decision,
)

__all__ = ["Decision"]