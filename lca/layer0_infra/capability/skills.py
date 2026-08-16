"""skills seam Definition — owns ctx.skills."""

from __future__ import annotations

from lca.contracts.protocols.operational_skills import SkillPackageStore
from lca.layer0_infra.capability.dispatch import ProviderDispatch


class SkillsService:
    """Service Definition：操作技能库。Consumer 只调 current()。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[SkillPackageStore]("skills")

    def register(self, name: str, provider: SkillPackageStore, *, activate: bool = False) -> None:
        self.providers.register(name, provider, activate=activate)

    def current(self) -> SkillPackageStore:
        return self.providers.current()
