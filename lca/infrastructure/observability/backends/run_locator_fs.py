"""FilesystemRunLocator —— ADR-0065 §七 / PR-5 默认实现 + ADR-0169 PR-27 升级。

布局(ADR-0169 PR-27 L10 / D9)::

    <root>/
    └── runs/
        └── <run_id>/                              # 不可猜测的目录名
            ├── <run_id>.spine.jsonl                # spine SSOT (ADR-0165.1 / 0167 D11 / PR-27)
            ├── journal.json                        # step-tree 主存储 (ADR-0164)
            ├── journal.narrative.md                # StepNarrativeWriter 产出
            ├── manifest.json
            ├── evidence/
            └── materializations/<generator-id>/<generator-version>/

跨 OS 路径差异(Linux/macOS vs Windows)封装在内部,调用方只见 ``RunLocator`` Protocol。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.registry.run_locator import RunLocator
from lca.infrastructure.observability.spine.sinks.naming import (
    spine_filename_for_run,
)


class FilesystemRunLocator(RunLocator):
    """fs 后端 RunLocator(0065 §七 / ADR-0169 PR-27)。"""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "runs").mkdir(parents=True, exist_ok=True)

    @property
    def storage_root(self) -> Path:
        return self._root

    # ── RunLocator 契约 ──────────────────────────────────────

    def run_dir(self, run_id: str) -> Path:
        return self._root / "runs" / run_id

    def journal_step_path(self, run_id: str) -> Path:
        """Step-tree 主存储路径(ADR-0164 Phase 2+)。"""
        return self.run_dir(run_id) / "journal.json"

    def events_path(self, run_id: str) -> Path:
        """SSOT 事件流路径(ADR-0165.1 / ADR-0167 D11 / ADR-0169 PR-27 L10)。

        PR-4 收口:只返回 spine 命名 ``<run_id>.spine.jsonl``,不再向旧
        layout 兜底;旧 run 的迁移由一次性 importer 完成(已迁移完毕)。
        """
        return self.run_dir(run_id) / spine_filename_for_run(run_id)

    def journal_narrative_path(self, run_id: str) -> Path:
        """Narrative markdown 路径(由 StepNarrativeWriter 写)。"""
        return self.run_dir(run_id) / "journal.narrative.md"

    def evidence_dir(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "evidence"

    def materialization_dir(
        self, run_id: str, *, generator_id: str, generator_version: str
    ) -> Path:
        return self.run_dir(run_id) / "materializations" / generator_id / generator_version

    def manifest_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "manifest.json"

__all__ = ["FilesystemRunLocator"]
