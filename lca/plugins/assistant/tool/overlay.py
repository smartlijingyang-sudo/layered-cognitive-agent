"""assistant.tool_overlay plugin —— ADR-0243 D4。

助理域 tool overlay 唯一实现：

- ``provides=("assistant.tool_overlay",)``;
- ``create`` / ``update`` —— 校验 ``ToolSpec``（frozen schema，未知字段
  fail-closed）⇒ 落盘 ``{home}/tools/<tool_id>/tool.json`` ⇒ manifest
  ``tools`` 索引 + ``revision_seq++`` ⇒ ``assistant.profile.revised`` EP;
- ``remove`` —— 删除 ``{home}/tools/<tool_id>/`` ⇒ manifest 修订 + EP;
- ``list_installed`` —— 扫 ``{home}/tools/``。

写路径 ⊆ ``{home}/tools/``；全局工具注册表只读不写。
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, ValidationError

from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_TOOL_OVERLAY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.assistant.tool_spec import ToolSpec
from lca.contracts.observability.closure.assistant_ep_closure import ASSISTANT_PROFILE_REVISED
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.assistant.tool_overlay import (
    AssistantToolOverlay,
    ToolInstallReceipt,
    ToolNotInstalled,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.assistant.events._events import AssistantProfileRevisedEventPayload
from lca.plugins.assistant.home._home_layout import (
    DEFAULT_TEMPLATE_ID,
    build_manifest,
    load_manifest,
    sha256_digest,
    write_manifest,
    write_revision_snapshot,
)

log = structlog.get_logger(__name__)

_TOOLS_DIGEST_PREFIX = "tools/"
"""manifest ``digests`` 中 tools 索引条目的 key 前缀（ADR-0243 D2 同构）。"""


class Config(BaseModel):
    """无配置字段：home 路径经 ``assistant.catalog`` 解析。"""

    model_config = ConfigDict(extra="forbid")


def _revision_of(manifest: Mapping[str, Any]) -> int:
    raw = manifest.get("revision_seq", 0)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return 0


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _tool_dir(home: Path, tool_id: str) -> Path:
    return home / "tools" / tool_id


def _read_tool_spec(tool_dir: Path) -> ToolSpec | None:
    """读 ``tool.json`` 并校验；缺失/损坏返回 None。"""
    path = tool_dir / "tool.json"
    if not path.is_file():
        return None
    try:
        return ToolSpec.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None


def _write_tool_spec(tool_dir: Path, spec: ToolSpec) -> None:
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.json").write_text(
        json.dumps(spec.model_dump(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


class _AssistantToolOverlayImpl(AssistantToolOverlay):
    """overlay 内部实现；通过 plugin ``setup`` 注入 catalog 与 emitter。

    单一职责：create / update / remove / list_installed。Home / manifest 真值
    属 Catalog；本类仅在写路径经 ``_home_layout`` 既有函数修订 manifest
    ``tools`` 索引（digest SSOT 纪律不变）。
    """

    def __init__(
        self,
        *,
        catalog: AssistantCatalog,
        event_emitter: Callable[[str, Mapping[str, Any]], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._emit = event_emitter
        self._clock = clock or (lambda: datetime.now(UTC))

    # ── 公开面 ────────────────────────────────────────────────────────

    async def create(
        self,
        assistant_id: str,
        spec: ToolSpec,
        *,
        actor: str = "system",
    ) -> ToolInstallReceipt:
        return await self._write(assistant_id, spec, replace=False, actor=actor)

    async def update(
        self,
        assistant_id: str,
        tool_id: str,
        spec: ToolSpec,
        *,
        actor: str = "system",
    ) -> ToolInstallReceipt:
        if tool_id != spec.name:
            raise ValueError(f"tool_id {tool_id!r} 与 ToolSpec.name {spec.name!r} 不一致")
        return await self._write(assistant_id, spec, replace=True, actor=actor)

    async def remove(
        self,
        assistant_id: str,
        tool_id: str,
        *,
        actor: str = "system",
    ) -> None:
        spec = self._catalog.get(assistant_id)
        home = Path(spec.home_path)
        tool_dir = _tool_dir(home, tool_id)
        if not tool_dir.is_dir():
            raise ToolNotInstalled(f"tool 未安装: assistant={assistant_id!r} tool={tool_id!r}")

        shutil.rmtree(tool_dir)
        manifest = load_manifest(home, assistant_id)
        new_revision_seq = _revision_of(manifest) + 1
        new_manifest = self._build_manifest(home, assistant_id, manifest, new_revision_seq)
        tools_section = manifest.get("tools")
        section: dict[str, Any] = dict(tools_section) if isinstance(tools_section, dict) else {}
        section.pop(tool_id, None)
        new_manifest["tools"] = section
        write_manifest(home, new_manifest)
        write_revision_snapshot(home, new_revision_seq, new_manifest)

        self._emit_profile_revised(
            AssistantProfileRevisedEventPayload(
                assistant_id=assistant_id,
                revision_seq=new_revision_seq,
                manifest_digest=str(new_manifest["manifest_digest"]),
                actor=actor,
                reason=f"remove_tool:{tool_id}",
                changes=(f"tools/{tool_id}",),
            )
        )

    def list_installed(self, assistant_id: str) -> tuple[ToolInstallReceipt, ...]:
        spec = self._catalog.get(assistant_id)
        home = Path(spec.home_path)
        manifest = load_manifest(home, assistant_id)
        tools_root = home / "tools"
        receipts: list[ToolInstallReceipt] = []
        if not tools_root.is_dir():
            return ()
        for child in sorted(tools_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            tool_spec = _read_tool_spec(child)
            if tool_spec is None:
                continue
            digest = sha256_digest(child / "tool.json")
            receipts.append(
                ToolInstallReceipt(
                    assistant_id=assistant_id,
                    tool_id=child.name,
                    digest=digest,
                    installed_at=_iso(self._clock()),
                    revision_seq=_revision_of(manifest),
                    manifest_digest=str(manifest.get("manifest_digest") or ""),
                    actor="system",
                    install_path=str(child),
                )
            )
        return tuple(receipts)

    # ── 内部 ──────────────────────────────────────────────────────────

    async def _write(
        self,
        assistant_id: str,
        spec: ToolSpec,
        *,
        replace: bool,
        actor: str,
    ) -> ToolInstallReceipt:
        catalog_spec = self._catalog.get(assistant_id)
        home = Path(catalog_spec.home_path)
        tool_dir = _tool_dir(home, spec.name)
        if tool_dir.exists() and not replace:
            raise ValueError(f"tool 已存在: assistant={assistant_id!r} tool={spec.name!r}")

        _write_tool_spec(tool_dir, spec)
        tool_digest = sha256_digest(tool_dir / "tool.json")
        manifest = load_manifest(home, assistant_id)
        new_revision_seq = _revision_of(manifest) + 1
        new_manifest = self._build_manifest(
            home,
            assistant_id,
            manifest,
            new_revision_seq,
            extra_digests={f"{_TOOLS_DIGEST_PREFIX}{spec.name}": tool_digest},
        )
        tools_section = manifest.get("tools")
        section: dict[str, Any] = dict(tools_section) if isinstance(tools_section, dict) else {}
        section[spec.name] = {
            "digest": tool_digest,
            "actor": actor,
        }
        new_manifest["tools"] = section
        write_manifest(home, new_manifest)
        write_revision_snapshot(home, new_revision_seq, new_manifest)

        self._emit_profile_revised(
            AssistantProfileRevisedEventPayload(
                assistant_id=assistant_id,
                revision_seq=new_revision_seq,
                manifest_digest=str(new_manifest["manifest_digest"]),
                actor=actor,
                reason="upsert_tool",
                changes=(f"tools/{spec.name}",),
            )
        )
        return ToolInstallReceipt(
            assistant_id=assistant_id,
            tool_id=spec.name,
            digest=tool_digest,
            installed_at=_iso(self._clock()),
            revision_seq=new_revision_seq,
            manifest_digest=str(new_manifest["manifest_digest"]),
            actor=actor,
            install_path=str(tool_dir),
        )

    def _build_manifest(
        self,
        home: Path,
        assistant_id: str,
        manifest: Mapping[str, Any],
        revision_seq: int,
        *,
        extra_digests: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        """重建 manifest：保留 skills / tools 索引的 digest 前缀并合并新摘要。"""
        previous_digests = manifest.get("digests")
        extra: dict[str, str] = {}
        if isinstance(previous_digests, dict):
            for name, value in previous_digests.items():
                if isinstance(value, str) and (
                    str(name).startswith("skills/") or str(name).startswith(_TOOLS_DIGEST_PREFIX)
                ):
                    extra[str(name)] = value
        tools_section = manifest.get("tools")
        section: dict[str, Any] = dict(tools_section) if isinstance(tools_section, dict) else {}
        for tool_id, entry in section.items():
            if isinstance(entry, dict) and isinstance(entry.get("digest"), str):
                extra.setdefault(f"{_TOOLS_DIGEST_PREFIX}{tool_id}", entry["digest"])
        if extra_digests:
            extra.update(extra_digests)
        new_manifest = build_manifest(
            assistant_id=assistant_id,
            template_id=str(manifest.get("template_id") or DEFAULT_TEMPLATE_ID),
            revision_seq=revision_seq,
            home=home,
            created_at=str(manifest.get("created_at") or "") or None,
            extra_digests=extra,
        )
        if "skills" in manifest:
            new_manifest["skills"] = manifest["skills"]
        return new_manifest

    def _emit_profile_revised(self, payload: AssistantProfileRevisedEventPayload) -> None:
        if self._emit is None:
            log.info(
                "assistant.tool_overlay.ep.no_emitter",
                ep=ASSISTANT_PROFILE_REVISED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_PROFILE_REVISED, payload.to_dict())


# ── Plugin manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.tool.overlay",
    provides=(ASSISTANT_TOOL_OVERLAY.key,),
    requires=(ASSISTANT_CATALOG.key, "event.bus"),
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.FILESYSTEM,),
    description=(
        "助理域 tool 定义/删除（ADR-0243 D4）：校验 ToolSpec 后只写本助理 "
        "Home 的 tools/ 子树，禁写全局工具注册表；删除不可逆。"
    ),
    test_suite="tests/plugins/assistant/test_tool_overlay.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca.plugins.assistant.tool_overlay.checked",
                "lca.plugins.assistant.tool_overlay.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key, "event.bus"),
        emits=(ASSISTANT_PROFILE_REVISED,),
        state_mutation="scoped",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """assistant.tool_overlay plugin boot。"""
    del config
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"assistant.tool_overlay requires {ASSISTANT_CATALOG.key} 为 AssistantCatalog, "
            f"得到 {type(catalog).__name__}"
        )

    def _emit(event: str, payload: Mapping[str, Any]) -> Any:
        from lca.infrastructure.observability.domain_event_publish import (
            publish_structural_event,
        )

        return publish_structural_event(
            execution_point=event,
            channel="fact",
            payload=dict(payload),
            producer=type(None),
        )

    overlay = _AssistantToolOverlayImpl(catalog=catalog, event_emitter=_emit)
    ctx.provide(ASSISTANT_TOOL_OVERLAY.key, overlay)


# 用于测试在不接 ctx 时直接构造
AssistantToolOverlayImpl = _AssistantToolOverlayImpl

__all__ = [
    "AssistantToolOverlayImpl",
    "Config",
    "setup",
]
