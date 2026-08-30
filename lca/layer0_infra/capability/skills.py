"""skills seam Definition — owns ctx.skills."""

from __future__ import annotations

from lca.contracts.protocols.operational_skills import SkillPackageInstaller
from lca.layer0_infra.capability.dispatch import ProviderDispatch


class SkillsService:
    """操作技能能力定义：以完整安装接缝调度提供方，消费者按需收窄为读取接缝。"""

    def __init__(self) -> None:
        self.providers = ProviderDispatch[SkillPackageInstaller]("skills")

    def register(
        self, name: str, provider: SkillPackageInstaller, *, activate: bool = False
    ) -> None:
        self.providers.register(name, provider, activate=activate)

    def current(self) -> SkillPackageInstaller:
        return self.providers.current()
