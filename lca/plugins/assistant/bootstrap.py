"""assistant.bootstrap plugin —— ADR-0187 §7 PR-4。

把 AssistantHome 的四个 bootstrap 配置面文件 + ``goals.yaml`` 投影进
``ContextManifest``；MEMORY.md / memory/ 不进（I-A13）。

- 投影目标字段：
  * ``workspace_instructions`` ← ``AGENTS.md``（SOUL/IDENTITY/USER/AGENTS 共占一组，
    AGENTS 是工具用法约定）
  * ``workspace_artifacts`` ← ``IDENTITY.md`` + ``goals.yaml`` 列表化
  * 另起两组 ``system`` ``ContextItem``：SOUL / USER
- 投影只读 + 不写文件（``EffectClass.NONE``）。
- ``provides=("assistant.bootstrap",)``；``requires=("assistant.catalog",)``。
- 失败语义：助理 home 缺失 / digest 不一致 ⇒ ValueError，不静默回落。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import ASSISTANT_BOOTSTRAP, ASSISTANT_CATALOG
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.perception import (
    ContextClass,
    ContextItem,
    ContextManifest,
    ItemKind,
)
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.assistant._home_layout import HomePaths, load_manifest

_BOOTSTRAP_FACE_FILES: tuple[str, ...] = (
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "AGENTS.md",
)
"""PR-4 投影目标文件：四个 bootstrap 配置面 + AGENTS 工具用法约定。"""

# MEMORY.md / memory/ 必须在投影外（I-A13：记忆面不参与 digest 不进 manifest）；
# 本插件代码不读取 / 不引用这两个字面路径；静态 grep 由 arch test 守住。


@dataclass(frozen=True)
class BootstrapProjection:
    """bootstrap 投影产物 = ContextManifest。

    PR-4 范围只产出 ContextManifest；后续 PR-5/7 可扩其他产物（指令摘要等）。
    """

    assistant_id: str
    manifest: ContextManifest

    def items(self) -> tuple[ContextItem, ...]:
        return self.manifest.items


def project_home_to_context_manifest(
    spec_home: Path,
    *,
    assistant_id: str,
) -> ContextManifest:
    """从 AssistantHome 物化 ContextManifest（PR-4 投影函数）。

    只读 ``SOUL.md`` / ``IDENTITY.md`` / ``USER.md`` / ``AGENTS.md`` + ``goals.yaml``
    五个文件；MEMORY.md / memory/ 不读取。失败（文件缺失 / 读错误 / goals.yaml
    非 dict）⇒ ``ValueError``（fail-closed；不允许回落空 manifest）。

    Precondition：``spec_home`` 是 AssistantHome 根路径（assistant_id 子目录）；
    digest 校验由 catalog 在 ``spec_home`` 之前完成；本函数不重算 digest，只读
    配置面文本并组装 ``ContextManifest.items``。
    """
    home = HomePaths(root=spec_home)
    manifest_raw = load_manifest(home.root, assistant_id)
    _ = manifest_raw  # presence check only; 投影阶段不重算 digest

    items: list[ContextItem] = []
    for face_name in _BOOTSTRAP_FACE_FILES:
        path = home.root / face_name
        if not path.is_file():
            raise ValueError(
                f"assistant {assistant_id!r} 配置面缺失 {face_name};无法 bootstrap 投影"
            )
        text = path.read_text(encoding="utf-8")
        if face_name == "AGENTS.md":
            kind: ItemKind = "workspace_instructions"
            content_class = ContextClass.INSTRUCTION
        elif face_name == "IDENTITY.md":
            kind = "workspace_artifacts"
            content_class = ContextClass.DATA
        else:
            # SOUL.md / USER.md → system prompt 一等公民（不进 prompt 时由
            # reasoner prompt assembler 决策；本 PR-4 只保证 ContextManifest
            # 携带完整文本与 provenance）。
            kind = "workspace_artifacts"
            content_class = ContextClass.SYSTEM
        items.append(
            ContextItem(
                kind=kind,
                payload={"name": face_name, "text": text},
                provenance=f"assistant.bootstrap.{assistant_id}",
                ref=None,
                extra={"assistant_id": assistant_id},
                content_class=content_class,
            )
        )

    goals_path = home.root / "goals.yaml"
    if not goals_path.is_file():
        raise ValueError(f"assistant {assistant_id!r} 缺 goals.yaml;无法 bootstrap 投影")
    goals_text = goals_path.read_text(encoding="utf-8")
    try:
        goals_parsed = yaml.safe_load(goals_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"assistant {assistant_id!r} goals.yaml YAML 解析失败:{exc}") from exc
    if goals_parsed is None:
        goals_payload: Any = []
        extra_fields: dict[str, Any] = {}
    elif isinstance(goals_parsed, list):
        goals_payload = goals_parsed
        extra_fields = {}
    elif isinstance(goals_parsed, Mapping):
        # 顶层 dict:``goals`` 键携带目标列表;其余顶层键透传到 extra
        goals_payload = goals_parsed.get("goals", [])
        extra_fields = {
            str(key): value for key, value in goals_parsed.items() if str(key) != "goals"
        }
    else:
        raise ValueError(
            f"assistant {assistant_id!r} goals.yaml 顶层必须是 list 或 mapping,得到 "
            f"{type(goals_parsed).__name__}"
        )

    payload: dict[str, Any] = {"name": "goals.yaml", "goals": goals_payload}
    if extra_fields:
        payload["extra"] = dict(extra_fields)
    items.append(
        ContextItem(
            kind="workspace_artifacts",
            payload=payload,
            provenance=f"assistant.bootstrap.{assistant_id}",
            ref=None,
            extra={"assistant_id": assistant_id},
            content_class=ContextClass.DATA,
        )
    )

    return ContextManifest(items=tuple(items))


def _memory_layer_excluded_from_items(items: tuple[ContextItem, ...]) -> bool:
    """守护：投影出的 ContextManifest 不含 MEMORY 痕迹（I-A13 + PR-4 新不变量）。

    静态检查：所有 item 的 payload 不应引用 ``memory/`` / ``MEMORY.md`` 字面；
    provenance 不含 ``memory`` 字段。允许 ``assistant.bootstrap.{id}`` 前缀。
    """
    for item in items:
        provenance = item.provenance
        if "memory" in provenance.lower() or "MEMORY" in provenance:
            return False
        payload = item.payload
        if isinstance(payload, Mapping):
            text_repr = str(payload)
            if "MEMORY.md" in text_repr or "/memory/" in text_repr:
                return False
    return True


class _BootstrapProjectionService:
    """bootstrap 投影的内部服务对象；plugin ``setup`` 通过 ``ctx.provide`` 暴露。

    单一职责：``project(assistant_id)`` 返回 ``BootstrapProjection``；
    其他 plugin / future Reasoner prompt assembler 通过 capability 入口消费。
    """

    def __init__(self, catalog: AssistantCatalog) -> None:
        self._catalog = catalog

    def project(self, assistant_id: str) -> BootstrapProjection:
        """拉 catalog 拿 spec（隐式触发 digest 校验），再投影。

        digest 不一致 ⇒ catalog 抛 ``AssistantDigestMismatch`` 透传，PR-4
        不吞错。
        """
        spec = self._catalog.get(assistant_id)
        manifest = project_home_to_context_manifest(
            spec_home=Path(spec.home_path),
            assistant_id=assistant_id,
        )
        if not _memory_layer_excluded_from_items(manifest.items):
            raise ValueError(
                f"assistant.bootstrap 投影含 MEMORY 字面（I-A13 违例）:assistant_id={assistant_id!r}"
            )
        return BootstrapProjection(assistant_id=assistant_id, manifest=manifest)


# ── Plugin Config ──────────────────────────────────────────────────────


class Config(BaseModel):
    """bootstrap plugin 无运行时 config；保留 Pydantic 形态对齐仓内插件范式。"""

    model_config = ConfigDict(extra="forbid")


# ── Plugin Manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.bootstrap",
    provides=(ASSISTANT_BOOTSTRAP.key,),
    requires=(ASSISTANT_CATALOG.key,),
    layer="L4",
    kind=PluginKind.SEAM,
    effects=(EffectClass.NONE,),
    description=(
        "把 AssistantHome 的 SOUL/IDENTITY/USER/AGENTS + goals.yaml 投影进 "
        "ContextManifest;MEMORY.md / memory/ 不参与投影(I-A13)"
    ),
    test_suite="tests/plugins/assistant/test_bootstrap.py",
    functional_group=FunctionalGroup.G1_IDENTITY,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G1_IDENTITY),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("assistant.bootstrap.project",)),
        observability=EvidenceContract(
            descriptors=("assistant.bootstrap.projected",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key,),
        emits=("assistant.bootstrap.projected",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """bootstrap plugin boot:取 catalog + 暴露 ``assistant.bootstrap`` 投影服务。

    仅读取 + 投影,不写文件,不订阅 EP,不持有可变缓存。catalog 必须先 boot。
    """
    del config
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"assistant.bootstrap requires {ASSISTANT_CATALOG.key} 为 AssistantCatalog, "
            f"得到 {type(catalog).__name__}"
        )
    service = _BootstrapProjectionService(catalog=catalog)
    ctx.provide(ASSISTANT_BOOTSTRAP.key, service)


# 用于测试在不接 ctx 时直接构造
BootstrapProjectionService = _BootstrapProjectionService

__all__ = [
    "BootstrapProjection",
    "BootstrapProjectionService",
    "Config",
    "project_home_to_context_manifest",
    "setup",
]
