"""Merge global operational skills with an assistant Home overlay (ADR-0187)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from lca.contracts.protocols.memory.operational_skills import (
    SkillIndexEntry,
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.settings.settings import SkillSettings

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.skill_overlay import AssistantSkillOverlay

_T = TypeVar("_T")


class AssistantMergedSkillStore(SkillPackageStore):
    """Assistant-scoped skill store: ``{home}/skills/`` 是完整有效技能集（ADR-0243 D1）。

    ADR-0243 起，assistant-bound run 的发现与激活只读 Home ``skills/``；
    全局 ``~/.lca/skills/`` 只是创建时硬链接物化的内容源，不再是运行时
    兜底层——删除 Home 条目后技能不会从全局重新出现（I-B16）。
    """

    def __init__(
        self,
        *,
        global_store: SkillPackageStore,
        overlay: AssistantSkillOverlay,
        assistant_id: str,
    ) -> None:
        self._global = global_store
        self._overlay = overlay
        self._assistant_id = assistant_id
        self._assistant_store: DiskSkillPackageStore | None = None

    @property
    def overlay(self) -> AssistantSkillOverlay:
        return self._overlay

    @property
    def assistant_id(self) -> str:
        return self._assistant_id

    def _assistant_disk_store(self) -> DiskSkillPackageStore | None:
        if self._assistant_store is not None:
            return self._assistant_store
        receipts = self._overlay.list_installed(self._assistant_id)
        if not receipts:
            return None
        skills_root = Path(receipts[0].install_path).parent
        if not skills_root.is_dir():
            return None
        self._assistant_store = DiskSkillPackageStore(SkillSettings(cache_dir=skills_root))
        return self._assistant_store

    def list_installed(self) -> tuple[SkillIndexEntry, ...]:
        assistant_store = self._assistant_disk_store()
        if assistant_store is None:
            return ()
        return assistant_store.list_installed()

    def _lookup(self, fetch: Callable[[SkillPackageStore], _T]) -> _T:
        """只查 Home 范围；未安装即抛 ``SkillNotFoundError``（无全局兜底）。"""
        assistant_store = self._assistant_disk_store()
        if assistant_store is None:
            raise SkillNotFoundError(f"assistant {self._assistant_id!r} 未安装任何技能")
        return fetch(assistant_store)

    def get(self, skill_id: str) -> SkillPackage:
        return self._lookup(lambda store: store.get(skill_id))

    def package_artifact_state(self, skill_id: str) -> str | None:
        """Home manifest 中该 skill 的 ``artifact_state``；无记录回 None。

        RA-055: ``SkillActivateTool`` 经此缝隙拿到与 overlay 同源的 manifest
        状态，用同一谓词（``is_activatable_state``）判定 content injection
        资格。duck-typed 调用 —— ``SkillPackageStore`` Protocol 本体不声明。
        """
        for receipt in self._overlay.list_installed(self._assistant_id):
            if receipt.skill_id == skill_id:
                return receipt.artifact_state
        return None

    def read_resource(self, skill_id: str, rel_path: str) -> str:
        return self._lookup(lambda store: store.read_resource(skill_id, rel_path))

    def resource_files(self, skill_id: str) -> dict[str, bytes]:
        return self._lookup(lambda store: store.resource_files(skill_id))

    def update_package_meta(
        self,
        skill_id: str,
        *,
        retired: bool | None = None,
        usage_count: int | None = None,
    ) -> SkillPackage:
        """写回装有该 skill 的 Home 磁盘 store（全局 store 只读，不兜底）。"""
        return self._lookup(
            lambda store: store.update_package_meta(
                skill_id, retired=retired, usage_count=usage_count
            )
        )


__all__ = ["AssistantMergedSkillStore"]
