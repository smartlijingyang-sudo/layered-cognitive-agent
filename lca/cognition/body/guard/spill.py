"""Tool result spill guard — DSH spill-policy analog (ADR-0197)."""

from __future__ import annotations

import json

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.act.tool.guards import ExecuteWrapper, ToolGuardContribution
from lca.contracts.protocols.act.tool.pipeline import ToolExecutionContext


def _payload_size(payload: object) -> int:
    if payload is None:
        return 0
    if isinstance(payload, str):
        return len(payload.encode("utf-8"))
    try:
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return len(repr(payload).encode("utf-8"))


class ToolResultSpillGuard(ToolGuardContribution):
    """Bound inline tool results; mark spill when payload exceeds budget."""

    def __init__(self, *, max_inline_bytes: int = 50_000) -> None:
        if max_inline_bytes < 1024:
            raise ValueError("max_inline_bytes must be >= 1024")
        self._max_inline_bytes = max_inline_bytes

    @property
    def id(self) -> str:
        return "guard.tool-result-spill"

    def wrap_execute(self, inner: ExecuteWrapper) -> ExecuteWrapper:
        return inner

    def transform_result(
        self, ctx: ToolExecutionContext, observation: Observation
    ) -> Observation:
        if observation.success is False or observation.payload is None:
            return observation
        size = _payload_size(observation.payload)
        if size <= self._max_inline_bytes:
            return observation
        preview = _preview_payload(observation.payload, limit=2048)
        extra = dict(observation.extra or {})
        extra.update(
            {
                "spill": True,
                "spill_guard": self.id,
                "original_bytes": size,
                "inline_preview": preview,
            }
        )
        return Observation(
            observation_id=observation.observation_id,
            success=observation.success,
            payload=preview,
            error=observation.error,
            extra=extra,
        )


def _preview_payload(payload: object, *, limit: int) -> str:
    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError):
            text = repr(payload)
    if len(text.encode("utf-8")) <= limit:
        return text
    encoded = text.encode("utf-8")
    return encoded[:limit].decode("utf-8", errors="ignore") + "\n…[spilled]"


__all__ = ["ToolResultSpillGuard"]
