"""Spine derivers sub-package — see ADR-0165 / ADR-0165.1.

Derivers are best-effort subscribers that produce secondary artefacts
(step-tree, narrative, live tail, ...) from the canonical event stream.
Per FD-2 their exceptions are contained by the spine.
"""

from lca.infrastructure.observability.spine.derivers.base import Deriver

__all__ = ["Deriver"]
