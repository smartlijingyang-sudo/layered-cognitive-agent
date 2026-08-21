"""RunDiff —— Coding Agent 只读 diff(两次 run 同 step 差异)。"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.coding_agent_tools import RunDiff, RunDiffTool
from lca.layer0_infra.observability.coding_agent_tools._helpers import (
    _inspector_events,
    _load_inspector_from_jsonl,
)


class RunDiffToolImpl(RunDiffTool):
    """只读 diff 两次 run。"""

    def __init__(self, jsonl_path: Path | str) -> None:
        self._path = Path(jsonl_path)

    def diff(self, *, run_id_a: str, run_id_b: str, step: int = 0) -> RunDiff:
        inspector = _load_inspector_from_jsonl(self._path)
        events = _inspector_events(inspector)
        events_a = [e for e in events if str(e.scope.run_id) == run_id_a and e.scope.step == step]
        events_b = [e for e in events if str(e.scope.run_id) == run_id_b and e.scope.step == step]
        prompt_hash_a = ""
        prompt_hash_b = ""
        for e in events_a:
            if isinstance(e.data, dict) and "prompt_hash" in e.data:
                prompt_hash_a = str(e.data["prompt_hash"])
                break
        for e in events_b:
            if isinstance(e.data, dict) and "prompt_hash" in e.data:
                prompt_hash_b = str(e.data["prompt_hash"])
                break
        return RunDiff(
            run_id_a=run_id_a,
            run_id_b=run_id_b,
            step=step,
            prompt_hash_a=prompt_hash_a,
            prompt_hash_b=prompt_hash_b,
            delta={},
        )


__all__ = ["RunDiffToolImpl"]
