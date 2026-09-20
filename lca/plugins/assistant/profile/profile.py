"""assistant.profile.backfill plugin —— ADR-0246 PR-5 用户画像回填。

系统从 identity/preference 结构化记忆回填 ``{home}/USER.md``，经
``AssistantCatalog.revise_profile`` 写盘（revision 快照自动产生），模型不
直接写该文件。``AssistantMemory`` 通过可选 ``profile_backfill`` 回调在写入
身份/偏好事实后触发本服务。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_PROFILE_BACKFILL
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.protocols.assistant.catalog import AssistantCatalog, ProfilePatch
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin

__all__ = [
    "Config",
    "ProfileBackfillService",
    "make_backfill_callback",
    "setup",
]

_ProfileBackfillCallback = Callable[[str, list[MemoryRecord]], Awaitable[None]]


def _render_user_profile(records: Sequence[MemoryRecord]) -> str:
    """把 identity/preference 记录渲染成 USER.md 画像。"""
    identity = [r.content for r in records if r.category is MemoryCategory.IDENTITY]
    preference = [r.content for r in records if r.category is MemoryCategory.PREFERENCE]
    lines = ["# 用户画像", ""]
    if identity:
        lines.append("## 身份")
        lines.extend(f"- {content}" for content in identity)
        lines.append("")
    if preference:
        lines.append("## 偏好")
        lines.extend(f"- {content}" for content in preference)
        lines.append("")
    return "\n".join(lines)


class ProfileBackfillService:
    """用户画像回填服务：identity/preference 事实 → ``{home}/USER.md``。"""

    def __init__(self, catalog: AssistantCatalog) -> None:
        self._catalog = catalog

    def backfill_from_records(
        self,
        assistant_id: str,
        records: Sequence[MemoryRecord],
    ) -> object | None:
        """回填 USER.md 并返回 ``PlanRevision``；无身份/偏好事实时返回 None。

        只读记忆记录，写 USER.md 走 ``revise_profile``（revision 快照由
        Catalog 负责）。同一次回填覆盖整个 USER.md 为用户画像。
        """
        identity_pref = [
            r for r in records if r.category in {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE}
        ]
        if not identity_pref:
            return None
        return self._catalog.revise_profile(
            assistant_id,
            ProfilePatch(user_md=_render_user_profile(identity_pref)),
        )


def make_backfill_callback(catalog: AssistantCatalog) -> _ProfileBackfillCallback:
    """构造 ``AssistantMemory(profile_backfill=...)`` 可用的异步回调。"""

    async def _backfill(assistant_id: str, records: list[MemoryRecord]) -> None:
        ProfileBackfillService(catalog).backfill_from_records(assistant_id, records)

    return _backfill


class Config(BaseModel):
    """profile 回填插件无运行时 config；保留 Pydantic 形态对齐仓内范式。"""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca.plugins.assistant.profile.profile",
    provides=(ASSISTANT_PROFILE_BACKFILL.key,),
    requires=(ASSISTANT_CATALOG.key,),
    layer="L4",
    kind=PluginKind.SEAM,
    effects=(EffectClass.NONE,),
    description="从 identity/preference 记忆回填 USER.md（系统行为，模型不直接写文件）。",
    test_suite="tests/plugins/assistant/test_profile_backfill.py",
    functional_group=FunctionalGroup.G1_IDENTITY,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G1_IDENTITY),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("assistant.profile.backfill",)),
        observability=EvidenceContract(
            descriptors=("assistant.profile.backfilled",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key,),
        emits=("assistant.profile.backfilled",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """boot:取 catalog + 暴露回填服务与回调工厂。"""
    del config
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"assistant.profile.backfill requires {ASSISTANT_CATALOG.key} 为 AssistantCatalog, "
            f"得到 {type(catalog).__name__}"
        )
    service = ProfileBackfillService(catalog=catalog)
    ctx.provide(ASSISTANT_PROFILE_BACKFILL.key, service)
