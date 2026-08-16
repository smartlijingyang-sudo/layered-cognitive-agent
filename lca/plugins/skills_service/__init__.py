"""Skills service plugin — provides the ``skills`` capability seam."""

from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest, ProviderMode

manifest = PluginManifest(
    id="lca.skills.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("skills",),
    provider_mode=ProviderMode.REGISTRY,
)

name = "lca.skills.service"
provides = "skills"


def apply(ctx: Any, config: Any) -> None:
    from lca.harness.skills import DiskSkillProvider, SkillCatalogService
    from lca.layer0_infra.capability.skills import SkillsService
    from lca.layer0_infra.skills.factory import resolve_skill_store

    store = resolve_skill_store()
    service = SkillsService()
    service.register("disk", store)
    ctx.mount("skills", service)
    ctx.mount("skill_catalog", SkillCatalogService(DiskSkillProvider(store)))
