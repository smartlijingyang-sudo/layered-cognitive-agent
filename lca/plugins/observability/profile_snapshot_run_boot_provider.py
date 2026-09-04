"""profile-snapshot-boot provider —— ADR-0096 MVA-3.

boot 期一次性写 ``traces/runs/<id>/profile_snapshot.json``;
plugin.inventory RuntimeObserved 不再写 journal。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict


class PluginSnapshotEntry(TypedDict):
    """profile_snapshot.json ``plugins[]`` slim 形态 —— P3 字段瘦身。

    只保留 ``id / layer / kind / effects``(4 字段),``description / config`` 等
    详细元数据随 ResolvedProfile 走 SSOT(``lca/harness/profile/resolve.py``),
    不在 snapshot 里重复。Reader 端按这 4 字段解析即可。
    """

    id: str
    layer: str
    kind: str
    effects: tuple[str, ...]


class RunBootSnapshot:
    """Boot-time snapshot writer —— writes static profile metadata once。

    Schema (loose — extension allowed for backward compat):
    ```json
    {
      "run_id": "...",
      "plan_ref": "...",
      "plugins": [{"id": "...", "layer": "...", "kind": "...", "effects": [...]}],
      "capabilities": {"llm": true, "tools": true, "journal_schemas": true},
      "control_plan": {"version": "v3", "phases": [...]}
    }
    ```
    """

    def write(
        self,
        *,
        run_id: str,
        outdir: Path,
        plan_ref: str,
        plugins: list[PluginSnapshotEntry],
        capabilities: dict[str, bool],
        control_plan: dict[str, object],
    ) -> Path:
        path = outdir / "profile_snapshot.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # plugins[] slim 化:list[str] → list[{id, layer, kind, effects}]
        slim_plugins = [
            {
                "id": str(entry["id"]),
                "layer": str(entry["layer"]),
                "kind": str(entry["kind"]),
                "effects": list(entry["effects"]),
            }
            for entry in plugins
        ]
        path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "plan_ref": plan_ref,
                    "plugins": slim_plugins,
                    "capabilities": capabilities,
                    "control_plan": control_plan,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return path
