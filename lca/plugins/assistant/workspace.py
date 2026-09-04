"""assistant.workspace plugin —— ADR-0187 §7 PR-4。

把 AssistantHome 的 ``workspace/`` 子目录绑成 ExecutionSpace 事实
（G2 投影，**不**直接世界写；世界写仍走既有 Body / CommandEnvelope（G7））。

- ``cwd`` = ``{home_path}/workspace/``（绝对路径）
- ``backend`` = ``"local"``
- ``acl_paths`` 默认 ⊆ ``{home_path}/workspace/``（I-A5）
- ``space_id`` = ``"asstspace:" + assistant_id``
- ``parent_space_id`` = profile 级 space（``assistant.workspace`` 默认 = None；
  RunSession 阶段由 route 层注入 profile_id）

plugin 声明 effect = ``FILESYSTEM``（物化 ExecutionSpace dataclass 含路径），
但实际不写盘 —— ``materialize_assistant_workspace`` 仅构造不可变 dataclass。
audit 端：路径校验读 ``Path.is_dir()`` 仅用于快速失败诊断。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_WORKSPACE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.act.execution_space import (
    ExecutionSpace,
    materialize_assistant_workspace,
)
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin

__all__ = [
    "Config",
    "WorkspaceMaterialization",
    "WorkspaceMaterializationService",
    "materialize_workspace_from_assistant",
    "setup",
]


@dataclass(frozen=True)
class WorkspaceMaterialization:
    """workspace 物化产物 = ExecutionSpace。

    与 :class:`lca.contracts.models.act.execution_space.ExecutionSpace` 同形；
    本包装保留 ``assistant_id`` 方便 caller 引用。
    """

    assistant_id: str
    space: ExecutionSpace


def materialize_workspace_from_assistant(
    *,
    assistant_id: str,
    home_path: str,
    parent_space_id: str | None = None,
) -> ExecutionSpace:
    """从 ``home_path`` 物化 ExecutionSpace（PR-4 helper）。

    - 校验 ``{home_path}/workspace/`` 存在（best-effort 快速失败诊断）
    - 调用 contracts 层 :func:`materialize_assistant_workspace`
    - 失败（workspace 子目录缺失）⇒ ``FileNotFoundError`
    """
    workspace_subdir = Path(home_path) / "workspace"
    if not workspace_subdir.is_dir():
        raise FileNotFoundError(
            f"assistant {assistant_id!r} workspace 子目录缺失: {workspace_subdir}"
        )
    return materialize_assistant_workspace(
        assistant_id=assistant_id,
        home_path=home_path,
        parent_space_id=parent_space_id,
    )


class _WorkspaceMaterializationService:
    """workspace 物化的内部服务对象；plugin ``setup`` 通过 ``ctx.provide`` 暴露。

    单一职责：``materialize(assistant_id, parent_space_id)`` 返回
    ``WorkspaceMaterialization``；其他 plugin / future RunSession 入口通过
    capability 入口消费。
    """

    def __init__(self, catalog: AssistantCatalog) -> None:
        self._catalog = catalog

    def materialize(
        self,
        assistant_id: str,
        parent_space_id: str | None = None,
    ) -> WorkspaceMaterialization:
        """拉 catalog 拿 spec（隐式触发 digest 校验），再物化 ExecutionSpace。

        digest 不一致 ⇒ catalog 抛 ``AssistantDigestMismatch`` 透传，PR-4
        不吞错。
        """
        spec = self._catalog.get(assistant_id)
        space = materialize_workspace_from_assistant(
            assistant_id=assistant_id,
            home_path=spec.home_path,
            parent_space_id=parent_space_id,
        )
        return WorkspaceMaterialization(assistant_id=assistant_id, space=space)


# ── Plugin Config ──────────────────────────────────────────────────────


class Config(BaseModel):
    """workspace plugin 无运行时 config；保留 Pydantic 形态对齐仓内插件范式。"""

    model_config = ConfigDict(extra="forbid")


# ── Plugin Manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.workspace",
    provides=(ASSISTANT_WORKSPACE.key,),
    requires=(ASSISTANT_CATALOG.key,),
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.FILESYSTEM,),
    description=(
        "绑定 cwd = home/workspace/ 到 ExecutionSpace 事实(ADR-0187 §3 D5);"
        "不直接世界写,ACL ⊆ home/workspace/(I-A5)"
    ),
    test_suite="tests/plugins/assistant/test_workspace.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("assistant.workspace.materialize",)),
        observability=EvidenceContract(
            descriptors=("assistant.workspace.materialized",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key,),
        emits=("assistant.workspace.materialized",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """workspace plugin boot:取 catalog + 暴露 ``assistant.workspace`` 物化服务。

    仅物化 ExecutionSpace dataclass,无 I/O 副作用,无 EP 发射,无 cache。
    catalog 必须先 boot。
    """
    del config
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"assistant.workspace requires {ASSISTANT_CATALOG.key} 为 AssistantCatalog, "
            f"得到 {type(catalog).__name__}"
        )
    service = _WorkspaceMaterializationService(catalog=catalog)
    ctx.provide(ASSISTANT_WORKSPACE.key, service)


# 用于测试在不接 ctx 时直接构造
WorkspaceMaterializationService = _WorkspaceMaterializationService
