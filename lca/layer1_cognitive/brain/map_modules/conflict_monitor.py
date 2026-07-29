"""ConflictMonitor content-aware default."""

from __future__ import annotations

from lca.contracts.decision import StructuredDecision
from lca.contracts.protocols import ConflictMonitor
from lca.contracts.state import TypedState


class SimpleConflictMonitor(ConflictMonitor):
    async def check(self, state: TypedState, candidates: list[StructuredDecision]) -> list[str]:
        del state
        if len(candidates) < 2:
            return []
        texts = {
            (c.response_text or c.rationale or "").strip().lower()
            for c in candidates
            if (c.response_text or c.rationale)
        }
        if len(texts) > 1:
            return ["content_disagreement"]
        if len({c.action_type for c in candidates}) > 1:
            return ["action_type_disagreement"]
        return []
