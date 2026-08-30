"""MinimalReproduction —— Coding Agent 只读 export 因果链 + evidence refs。"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.coding_agent_tools import (
    MinimalReproductionPackage,
    MinimalReproductionTool,
)
from lca.infrastructure.observability.coding_agent_tools._helpers import (
    _load_inspector_from_jsonl,
)


class MinimalReproduction(MinimalReproductionTool):
    """只读 export 失败因果链 + evidence refs。"""

    def __init__(self, jsonl_path: Path | str) -> None:
        self._path = Path(jsonl_path)

    def export(self, *, run_id: str) -> MinimalReproductionPackage:
        inspector = _load_inspector_from_jsonl(self._path)
        rendered = inspector.export_minimal_reproduction(run_id=run_id)
        # rendered: tuple[dict, ...];first entry is the failure itself
        first = rendered[0] if rendered else {}
        failure_seq = int(first.get("seq", 0))
        failure_type = str(first.get("type", ""))
        causal_chain = tuple(
            int(e.get("seq", 0)) for e in inspector.explain_failure(run_id=run_id).causal_chain
        )
        return MinimalReproductionPackage(
            failure_seq=failure_seq,
            failure_event_type=failure_type,
            causal_chain=causal_chain,
            evidence_refs=(),
        )


__all__ = ["MinimalReproduction"]
