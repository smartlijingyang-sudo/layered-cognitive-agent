"""profile-snapshot-boot provider —— ADR-0096 MVA-3.

boot 期一次性写 ``traces/runs/<id>/profile_snapshot.json``;
plugin.inventory RuntimeObserved 不再写 journal。
"""

from __future__ import annotations

import json
from pathlib import Path


class RunBootSnapshot:
    """Boot-time snapshot writer —— writes static profile metadata once。

    Schema (loose — extension allowed for backward compat):
    ```json
    {
      "run_id": "...",
      "plan_ref": "...",
      "plugins": ["lca-llm", "lca-tools", ...],
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
        plugins: list[str],
        capabilities: dict[str, bool],
        control_plan: dict[str, object],
    ) -> Path:
        from lca.infrastructure.observability.backends.run_locator_fs import (
            FilesystemRunLocator,
        )

        path = FilesystemRunLocator(outdir).profile_snapshot_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "plan_ref": plan_ref,
                    "plugins": plugins,
                    "capabilities": capabilities,
                    "control_plan": control_plan,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return path
