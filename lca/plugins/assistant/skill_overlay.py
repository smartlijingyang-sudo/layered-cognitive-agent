"""assistant.skill_overlay plugin —— ADR-0187 §7 PR-6。

助理域 skill overlay 唯一实现:

- ``provides=("assistant.skill_overlay",)``;
- ``install`` —— 经 ADR-0048 ``SkillImporter`` 拉取/校验 ⇒ ADR-0067 三闸
  (identity / invariant / experiment) ⇒ ``DRAFT → VERIFIED`` ⇒ 落盘
  ``{home}/skills/<skill_id>/`` ⇒ manifest skills 索引 + ``revision_seq++``
  ⇒ 发 ``assistant.skill.installed`` EP;
- ``list_installed`` —— 扫 ``{home}/skills/``;
- ``activate`` —— 仅接受 VERIFIED/ACTIVE 包;未验证拒收(发
  ``assistant.skill.activated`` EP,不写 Home)。

写路径 ⊆ ``{home}/skills/``;``~/.lca/skills/`` 全局 store 只读不写。
拉取绑定到 Home 内 staging 的 ``DiskSkillPackageStore``,网络行为仍由
0048 机制(host allowlist / 大小上限 / ZIP 安全解压)治理。
"""

from __future__ import annotations

import contextlib
import json
import shutil
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.artifact_state import ArtifactState
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_SKILL_OVERLAY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.harness.journal.artifact import (
    CapabilityArtifact,
    make_capability_artifact,
    migrate_to_verified,
)
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_SKILL_ACTIVATED,
    ASSISTANT_SKILL_INSTALLED,
)
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.assistant.skill_overlay import (
    AssistantSkillOverlay,
    SkillActivationReceipt,
    SkillInstallReceipt,
    SkillNotInstalled,
    SkillNotVerified,
    SkillSource,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.memory.operational_skills import (
    SKILL_MAX_CONTENT_CHARS,
    SKILL_MAX_RESOURCES,
    SkillImporter,
    SkillImportError,
    SkillPackage,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.infrastructure.skills.disk_store import (
    DiskSkillPackageStore,
    safe_rel_path,
    sanitize_skill_id,
)
from lca.infrastructure.skills.frontmatter import skill_title, split_frontmatter
from lca.infrastructure.skills.http_importer import HttpSkillImporter
from lca.infrastructure.skills.settings import SkillSettings
from lca.plugins.assistant._events import (
    AssistantSkillActivatedEventPayload,
    AssistantSkillInstalledEventPayload,
)
from lca.plugins.assistant._home_layout import (
    DEFAULT_TEMPLATE_ID,
    build_manifest,
    load_manifest,
    write_manifest,
)

log = structlog.get_logger(__name__)


# ── 常量 ─────────────────────────────────────────────────────────────

_STAGING_DIR_NAME = ".staging"
"""Home 内 staging 子目录名(隐藏目录;``list_installed`` 跳过)。"""

_SKILLS_DIGEST_PREFIX = "skills/"
"""manifest ``digests`` 中 skills 索引条目的 key 前缀。"""

_ACTIVATABLE_STATES = frozenset({ArtifactState.VERIFIED.value, ArtifactState.ACTIVE.value})
"""``activate`` 接受的状态闭集(ADR-0187 §3 D6)。"""


# ── Plugin 配置 ───────────────────────────────────────────────────────


class Config(BaseModel):
    """无配置字段:home 路径经 ``assistant.catalog`` 解析,根路径由
    Catalog 的 Profile 注入拥有;本插件不读 ``os.environ``。"""

    model_config = ConfigDict(extra="forbid")


# ── 0048 拉取 seam ───────────────────────────────────────────────────


def _default_url_importer(staging_root: Path) -> SkillImporter:
    """默认 URL 拉取器:0048 ``HttpSkillImporter`` 绑定 Home 内 staging store。

    ``cache_dir`` 显式注入 = 拉取产物只落 staging,不触达全局
    skills store(pydantic-settings 中 init 值优先于环境变量)。
    """
    return HttpSkillImporter(
        store=DiskSkillPackageStore(SkillSettings(cache_dir=staging_root)),
        settings=SkillSettings(cache_dir=staging_root),
    )


def _import_local_path(staging_root: Path, local_path: str) -> SkillPackage:
    """本地目录源:读 ``SKILL.md`` + 资源,经 0048 ``install_package`` 校验落 staging。

    校验(大小上限 / 资源路径安全 / skill_id 合法性)全部由
    ``DiskSkillPackageStore.install_package`` 执行,与 URL 路径同一入口。
    """
    src = Path(local_path)
    if not src.is_dir():
        raise SkillImportError(f"local_path 不是已存在目录: {local_path}")
    skill_md = next((p for p in (src / "SKILL.md", src / "skill.md") if p.is_file()), None)
    if skill_md is None:
        raise SkillImportError(f"local_path 缺 SKILL.md: {local_path}")
    text = skill_md.read_text(encoding="utf-8")
    resources: dict[str, bytes] = {}
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path == skill_md:
            continue
        rel = safe_rel_path(str(path.relative_to(src)))
        if rel:
            resources[rel] = path.read_bytes()
    meta, _ = split_frontmatter(text)
    skill_id = sanitize_skill_id(skill_title(meta, src.name))
    store = DiskSkillPackageStore(SkillSettings(cache_dir=staging_root))
    return store.install_package(
        skill_id=skill_id,
        skill_md_text=text,
        resource_files=resources,
        source_url=str(src),
    )


# ── 0067 三闸 ────────────────────────────────────────────────────────


def _gate_package(package: SkillPackage) -> CapabilityArtifact:
    """ADR-0067 三闸 + ``DRAFT → VERIFIED`` 迁移;任一失败抛 ``SkillImportError``。

    - identity —— skill_id 合法、内容 digest 固定、来源 provenance 非空;
    - invariant —— 0048 结构上限(内容长度 / 资源数 / 路径白名单)不破坏;
    - experiment —— 落点限助理域 scope,安装不携带任何 grant 扩张。

    状态机迁移经 ``migrate_to_verified``(0067 唯一提升入口);非法迁移
    抛 ``InvalidStateTransitionError``。
    """
    if not package.skill_id or sanitize_skill_id(package.skill_id) != package.skill_id:
        raise SkillImportError(f"identity 闸失败: skill_id 非法 {package.skill_id!r}")
    if not package.content_hash:
        raise SkillImportError("identity 闸失败: 包缺内容 digest")
    if not package.source_url:
        raise SkillImportError("identity 闸失败: 缺安装来源")
    if len(package.content) > SKILL_MAX_CONTENT_CHARS:
        raise SkillImportError("invariant 闸失败: SKILL.md 超过上限")
    if len(package.resource_paths) > SKILL_MAX_RESOURCES:
        raise SkillImportError("invariant 闸失败: 资源数超过上限")
    for rel in package.resource_paths:
        if not rel or safe_rel_path(rel) != rel:
            raise SkillImportError(f"invariant 闸失败: 资源路径非法 {rel!r}")

    artifact = make_capability_artifact(
        logical_id=f"assistant.skill:{package.skill_id}",
        content=package.content_hash,
        scope=Scope.AGENT,
        state=ArtifactState.DRAFT,
        grants=(),
        metadata={"source_url": package.source_url, "version": package.version},
    )
    if artifact.grants:
        # 安装永不扩权:外部包脚本执行仍受沙箱与既有 grant 约束(ADR-0187 §3 D6)
        raise SkillImportError("experiment 闸失败: 安装不得携带 grant")
    if artifact.scope is not Scope.AGENT:
        raise SkillImportError("experiment 闸失败: 落点 scope 限助理域")
    return migrate_to_verified(artifact)


def _place_package(staging_root: Path, skills_root: Path, skill_id: str) -> Path:
    """把 staging 中的完整包移入 ``{home}/skills/<skill_id>/``(覆盖式重装)。"""
    src = staging_root / skill_id
    if not (src / "manifest.json").is_file() or not (src / "SKILL.md").is_file():
        raise SkillImportError(f"staging 包不完整: {src}")
    skills_root.mkdir(parents=True, exist_ok=True)
    dest = skills_root / skill_id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(src), str(dest))
    return dest


def _package_digest(package: SkillPackage) -> str:
    """``sha256:<hex>`` 形式的包内容摘要(manifest digests 条目同形)。"""
    digest = package.content_hash
    return digest if digest.startswith("sha256:") else f"sha256:{digest}"


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _revision_of(manifest: Mapping[str, Any]) -> int:
    raw = manifest.get("revision_seq", 0)
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return 0


# ── Overlay 实现 ─────────────────────────────────────────────────────


class _AssistantSkillOverlayImpl(AssistantSkillOverlay):
    """overlay 内部实现;通过 plugin ``setup`` 注入 catalog 与 emitter。

    单一职责:install / list_installed / activate。Home / manifest 真值
    属 Catalog;本类仅在 install 路径经 ``_home_layout`` 既有函数修订
    manifest skills 索引(digest SSOT 纪律不变)。
    """

    def __init__(
        self,
        *,
        catalog: AssistantCatalog,
        event_emitter: Callable[[str, Mapping[str, Any]], Any] | None = None,
        url_importer_factory: Callable[[Path], SkillImporter] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._emit = event_emitter
        self._url_importer_factory = url_importer_factory or _default_url_importer
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ── 公开面 ────────────────────────────────────────────────────────

    async def install(
        self,
        assistant_id: str,
        source: SkillSource,
        *,
        actor: str = "system",
    ) -> SkillInstallReceipt:
        spec = self._catalog.get(assistant_id)  # digest 校验 fail-closed
        home = Path(spec.home_path)
        skills_root = home / "skills"
        staging_root = skills_root / _STAGING_DIR_NAME / uuid.uuid4().hex
        try:
            package = await self._fetch(staging_root, source)
            artifact = _gate_package(package)
            install_path = _place_package(staging_root, skills_root, package.skill_id)
            manifest = self._record_install(
                home=home,
                assistant_id=assistant_id,
                package=package,
                artifact=artifact,
                source=source,
                actor=actor,
            )
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
            staging_parent = skills_root / _STAGING_DIR_NAME
            if staging_parent.is_dir():
                with contextlib.suppress(OSError):
                    staging_parent.rmdir()  # 仅当空目录时收掉,不留空壳

        installed_at = _iso(self._clock())
        payload = AssistantSkillInstalledEventPayload(
            assistant_id=assistant_id,
            revision_seq=_revision_of(manifest),
            manifest_digest=str(manifest["manifest_digest"]),
            actor=actor,
            skill_id=package.skill_id,
            skill_digest=_package_digest(package),
            artifact_state=artifact.state.value,
            source=source.reference,
            version=package.version,
            installed_at=installed_at,
        )
        self._emit_installed(payload)
        return SkillInstallReceipt(
            assistant_id=assistant_id,
            skill_id=package.skill_id,
            version=package.version,
            digest=_package_digest(package),
            artifact_state=artifact.state.value,
            installed_at=installed_at,
            revision_seq=_revision_of(manifest),
            manifest_digest=str(manifest["manifest_digest"]),
            actor=actor,
            source=source.reference,
            install_path=str(install_path),
        )

    def list_installed(self, assistant_id: str) -> tuple[SkillInstallReceipt, ...]:
        spec = self._catalog.get(assistant_id)  # fail-closed digest 校验 + home 解析
        home = Path(spec.home_path)
        manifest = load_manifest(home, assistant_id)
        skills_section = manifest.get("skills")
        section: Mapping[str, Any] = skills_section if isinstance(skills_section, dict) else {}
        receipts: list[SkillInstallReceipt] = []
        skills_root = home / "skills"
        if not skills_root.is_dir():
            return ()
        for child in sorted(skills_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            entry = section.get(child.name)
            receipts.append(
                _receipt_from_disk(
                    child,
                    entry if isinstance(entry, dict) else None,
                    assistant_id=assistant_id,
                    revision_seq=_revision_of(manifest),
                    manifest_digest=str(manifest.get("manifest_digest") or ""),
                )
            )
        return tuple(receipts)

    def activate(
        self,
        assistant_id: str,
        skill_id: str,
        *,
        actor: str = "system",
    ) -> SkillActivationReceipt:
        spec = self._catalog.get(assistant_id)  # fail-closed digest 校验 + home 解析
        home = Path(spec.home_path)
        manifest = load_manifest(home, assistant_id)
        skill_dir = home / "skills" / sanitize_skill_id(skill_id)
        if not skill_dir.is_dir():
            raise SkillNotInstalled(f"skill 未安装: assistant={assistant_id!r} skill={skill_id!r}")
        skills_section = manifest.get("skills")
        section: Mapping[str, Any] = skills_section if isinstance(skills_section, dict) else {}
        entry = section.get(skill_id)
        state = str(entry.get("artifact_state") or "") if isinstance(entry, dict) else ""
        if state not in _ACTIVATABLE_STATES:
            raise SkillNotVerified(
                f"skill 未过 0067 闸门,不可 activate: assistant={assistant_id!r} "
                f"skill={skill_id!r} state={state or '(无索引记录)'}"
            )
        receipt = SkillActivationReceipt(
            assistant_id=assistant_id,
            skill_id=skill_id,
            activation_id=f"act_{uuid.uuid4().hex[:12]}",
            activated_at=_iso(self._clock()),
            revision_seq=_revision_of(manifest),
            manifest_digest=str(manifest.get("manifest_digest") or ""),
            actor=actor,
            artifact_state=state,
        )
        self._emit_activated(
            AssistantSkillActivatedEventPayload(
                assistant_id=assistant_id,
                revision_seq=receipt.revision_seq,
                manifest_digest=receipt.manifest_digest,
                actor=actor,
                skill_id=skill_id,
                activation_id=receipt.activation_id,
                artifact_state=state,
                activated_at=receipt.activated_at,
            )
        )
        return receipt

    # ── 内部 ──────────────────────────────────────────────────────────

    async def _fetch(self, staging_root: Path, source: SkillSource) -> SkillPackage:
        """0048 拉取/校验进 staging;网络路径经 ``SkillImporter.import_from_url``。"""
        if source.url.strip():
            importer = self._url_importer_factory(staging_root)
            return await importer.import_from_url(source.url)
        return _import_local_path(staging_root, source.local_path)

    def _record_install(
        self,
        *,
        home: Path,
        assistant_id: str,
        package: SkillPackage,
        artifact: CapabilityArtifact,
        source: SkillSource,
        actor: str,
    ) -> dict[str, object]:
        """manifest skills 索引修订:``digests`` 条目 + ``revision_seq++`` + 写盘。"""
        manifest = load_manifest(home, assistant_id)
        previous_digests = manifest.get("digests")
        extra: dict[str, str] = {}
        if isinstance(previous_digests, dict):
            extra = {
                str(name): str(value)
                for name, value in previous_digests.items()
                if isinstance(value, str) and str(name).startswith(_SKILLS_DIGEST_PREFIX)
            }
        package_digest = _package_digest(package)
        extra[f"{_SKILLS_DIGEST_PREFIX}{package.skill_id}"] = package_digest

        new_manifest = build_manifest(
            assistant_id=assistant_id,
            template_id=str(manifest.get("template_id") or DEFAULT_TEMPLATE_ID),
            revision_seq=_revision_of(manifest) + 1,
            home=home,
            created_at=str(manifest.get("created_at") or "") or None,
            extra_digests=extra,
        )
        skills_section = manifest.get("skills")
        section: dict[str, Any] = dict(skills_section) if isinstance(skills_section, dict) else {}
        section[package.skill_id] = {
            "digest": package_digest,
            "artifact_state": artifact.state.value,
            "version": package.version,
            "source": source.reference,
            "installed_at": _iso(self._clock()),
            "actor": actor,
        }
        new_manifest["skills"] = section
        write_manifest(home, new_manifest)
        return new_manifest

    def _emit_installed(self, payload: AssistantSkillInstalledEventPayload) -> None:
        """发 ``assistant.skill.installed`` EP;无 emitter 时仅 log(单元测试路径)。"""
        if self._emit is None:
            log.info(
                "assistant.skill_overlay.ep.no_emitter",
                ep=ASSISTANT_SKILL_INSTALLED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_SKILL_INSTALLED, payload.to_dict())

    def _emit_activated(self, payload: AssistantSkillActivatedEventPayload) -> None:
        """发 ``assistant.skill.activated`` EP;无 emitter 时仅 log(单元测试路径)。"""
        if self._emit is None:
            log.info(
                "assistant.skill_overlay.ep.no_emitter",
                ep=ASSISTANT_SKILL_ACTIVATED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_SKILL_ACTIVATED, payload.to_dict())


def _receipt_from_disk(
    skill_dir: Path,
    entry: Mapping[str, Any] | None,
    *,
    assistant_id: str,
    revision_seq: int,
    manifest_digest: str,
) -> SkillInstallReceipt:
    """从 ``{home}/skills/<skill_id>/`` 重建回执。

    ``entry`` = Home manifest skills 索引记录;缺失(手动落盘)⇒
    ``artifact_state="draft"`` —— 可见但不可 activate(fail-closed)。
    """
    store_manifest: dict[str, Any] = {}
    store_manifest_path = skill_dir / "manifest.json"
    if store_manifest_path.is_file():
        try:
            loaded = json.loads(store_manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                store_manifest = loaded
        except (OSError, ValueError):
            store_manifest = {}

    if entry is not None:
        state = str(entry.get("artifact_state") or "draft")
        digest = str(entry.get("digest") or "")
        installed_at = str(entry.get("installed_at") or "")
        actor = str(entry.get("actor") or "system")
        source = str(entry.get("source") or "")
        version = str(entry.get("version") or "")
    else:
        state = ArtifactState.DRAFT.value
        digest = ""
        installed_at = str(store_manifest.get("imported_at") or "")
        actor = "system"
        source = str(store_manifest.get("source_url") or "")
        version = str(store_manifest.get("version") or "")
    if not digest:
        content_hash = str(store_manifest.get("content_hash") or "")
        digest = f"sha256:{content_hash}" if content_hash else "sha256:unknown"
    return SkillInstallReceipt(
        assistant_id=assistant_id,
        skill_id=skill_dir.name,
        version=version,
        digest=digest,
        artifact_state=state,
        installed_at=installed_at,
        revision_seq=revision_seq,
        manifest_digest=manifest_digest,
        actor=actor,
        source=source,
        install_path=str(skill_dir),
    )


# ── Plugin manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.skill_overlay",
    provides=(ASSISTANT_SKILL_OVERLAY.key,),
    requires=(ASSISTANT_CATALOG.key, "event.bus"),
    layer="L4",
    kind=PluginKind.PROVIDER,
    # capability_plan_resolver 禁止多 effect class;网络拉取是 0048
    # SkillImporter 的 effect 面,本插件自身的持久副作用 = Home skills 写。
    effects=(EffectClass.FILESYSTEM,),
    description=(
        "助理域 skill 安装/激活(ADR-0187 §7 PR-6):0048 拉取 + 0067 三闸,"
        "只写本助理 Home 的 skills 子树,禁写全局 skills store;"
        "未验证包不可 activate。"
    ),
    test_suite="tests/plugins/assistant/test_skill_overlay.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca.plugins.assistant.skill_overlay.checked",
                "lca.plugins.assistant.skill_overlay.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key, "event.bus"),
        emits=(ASSISTANT_SKILL_INSTALLED, ASSISTANT_SKILL_ACTIVATED),
        state_mutation="reducer-only",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """assistant.skill_overlay plugin boot。

    行为契约:

    1. ``ctx.require(assistant.catalog)`` 取 Catalog(先决依赖;DAG 保证
       catalog 先 boot);isinstance 校验 fail-loud。
    2. EP 发射走 audited ``ctx.emit``;``assistant.*`` EP 描述符由
       catalog plugin boot 期统一补登(12 个),本插件不重复注册。
    3. 拉取器默认 ``_default_url_importer``(0048 HttpSkillImporter 绑定
       Home 内 staging store);测试可经实现类构造参数替换。
    """
    del config
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"assistant.skill_overlay requires {ASSISTANT_CATALOG.key} 为 AssistantCatalog, "
            f"得到 {type(catalog).__name__}"
        )

    def _emit(event: str, payload: Mapping[str, Any]) -> Any:
        return ctx.emit(event, dict(payload))

    overlay = _AssistantSkillOverlayImpl(catalog=catalog, event_emitter=_emit)
    ctx.provide(ASSISTANT_SKILL_OVERLAY.key, overlay)


# 用于测试在不接 ctx 时直接构造
AssistantSkillOverlayImpl = _AssistantSkillOverlayImpl

__all__ = [
    "AssistantSkillOverlayImpl",
    "Config",
    "setup",
]
