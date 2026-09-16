"""MinimalReproduction —— Coding Agent 只读 export 因果链 + evidence refs。"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.infra.coding_agent_tools import (
    MinimalReproductionPackage,
    MinimalReproductionTool,
)
from lca.plugins.tools.diagnostics.helpers._helpers import (
    _load_inspector_from_jsonl,
)


class MinimalReproduction(MinimalReproductionTool):
    """只读 export 失败因果链 + evidence refs。"""

    def __init__(self, jsonl_path: Path | str) -> None:
        self._path = Path(jsonl_path)

    def export(self, *, run_id: str) -> MinimalReproductionPackage:
        inspector = _load_inspector_from_jsonl(self._path)
        rendered = inspector.export_minimal_reproduction(run_id=run_id)
        chain = inspector.explain_failure(run_id=run_id).causal_chain
        # The anchor is the newest event in its own causal chain, so
        # ``failure_seq`` and ``causal_chain`` always name the same failure.
        # Reading ``rendered[0]`` instead reported the ledger's first event
        # whenever the run had nothing to reproduce.
        anchor_seq = max(chain) if chain else 0
        anchor = next(
            (item for item in rendered if int(item.get("seq", 0)) == anchor_seq),
            {},
        )
        return MinimalReproductionPackage(
            failure_seq=anchor_seq if anchor else 0,
            failure_event_type=str(anchor.get("type", "")) if anchor else "",
            causal_chain=chain,
            evidence_refs=(),
        )


__all__ = ["MinimalReproduction"]
