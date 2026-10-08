"""assistant.skill_overlay —— Overlay 实现类。

``_AssistantSkillOverlayImpl`` 承载 install / list_installed / activate /
remove / edit / relink_global_skills;manifest skills 索引修订与 EP 发射仍在此实现。
"""

from __future__ import annotations

import contextlib
import json
import shutil
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import structlog

from lca.contracts.atoms.artifact.state import is_activatable_state
from lca.contracts.atoms.ids.ids import utc_now_iso
from lca.contracts.harness.journal.artifact import CapabilityArtifact
from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_PROFILE_REVISED,
    ASSISTANT_SKILL_ACTIVATED,
    ASSISTANT_SKILL_INSTALLED,
)
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.assistant.skill_overlay import (
    AssistantSkillOverlay,
    SkillActivationReceipt,
    SkillInstallReceipt,
    SkillNotInstalledError,
    SkillNotVerifiedError,
    SkillRelinkReport,
    SkillSource,
)
from lca.contracts.protocols.memory.operational_skills import (
    SkillImporter,
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)
from lca.infrastructure.skills.disk.store import (
    DiskSkillPackageStore,
    safe_rel_path,
    sanitize_skill_id,
)
from lca.infrastructure.skills.settings.settings import SkillSettings, get_skill_settings
from lca.plugins.assistant.events._events import (
    AssistantProfileRevisedEventPayload,
    AssistantSkillActivatedEventPayload,
    AssistantSkillInstalledEventPayload,
    emit_assistant_ep_or_log,
)
from lca.plugins.assistant.home._home_layout import (
    DEFAULT_TEMPLATE_ID,
    build_manifest,
    load_manifest,
    write_manifest,
    write_revision_snapshot,
)
from lca.plugins.assistant.skill.overlay.gating import (
    _GLOBAL_LINK_SOURCE,
    _SKILLS_DIGEST_PREFIX,
    _STAGING_DIR_NAME,
    _gate_package,
    _is_global_link,
    _link_global_package,
    _mark_local,
    _package_digest,
    _place_package,
    _revision_of,
)
from lca.plugins.assistant.skill.overlay.importing import (
    _default_url_importer,
    _import_local_path,
)
from lca.plugins.assistant.skill.overlay.receipts import _receipt_from_disk

log = structlog.get_logger(__package__)


def _default_global_store() -> SkillPackageStore:
    """默认全局技能库读缝（ADR-0243 D1:全局库是只读内容源）。

    直接构造 ``DiskSkillPackageStore(get_skill_settings())``,**不**经
    ``resolve_skill_store()``:后者附带 ``ensure_bundled_skills``,会从 repo
    工作树写全局库。re-link 只按全局库当前状态升级已链接 Home——把 bundled
    技能刷进内容源是 boot 期职责,混进升级路径会让「重链」偷偷变成「先改源」。
    """
    return DiskSkillPackageStore(get_skill_settings())


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
        global_store_factory: Callable[[], SkillPackageStore] | None = None,
    ) -> None:
        self._catalog = catalog
        self._emit = event_emitter
        self._url_importer_factory = url_importer_factory or _default_url_importer
        # 注入的是工厂而非实例:构造 DiskSkillPackageStore 会 mkdir 全局根,
        # 没有 global_link 条目的 Home 不该因此触碰全局库。
        self._global_store_factory = global_store_factory or _default_global_store

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

        installed_at = utc_now_iso()
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
            raise SkillNotInstalledError(f"skill 未安装: assistant={assistant_id!r} skill={skill_id!r}")
        skills_section = manifest.get("skills")
        section: Mapping[str, Any] = skills_section if isinstance(skills_section, dict) else {}
        entry = section.get(skill_id)
        state = str(entry.get("artifact_state") or "") if isinstance(entry, dict) else ""
        if not is_activatable_state(state):  # RA-055: 与 activate_skill 共用同一谓词
            raise SkillNotVerifiedError(
                f"skill 未过 0067 闸门,不可 activate: assistant={assistant_id!r} "
                f"skill={skill_id!r} state={state or '(无索引记录)'}"
            )
        receipt = SkillActivationReceipt(
            assistant_id=assistant_id,
            skill_id=skill_id,
            activation_id=f"act_{uuid.uuid4().hex[:12]}",
            activated_at=utc_now_iso(),
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

    async def remove(
        self,
        assistant_id: str,
        skill_id: str,
        *,
        actor: str = "system",
    ) -> None:
        """删除已安装 skill（ADR-0242 D6）：删盘 + manifest 修订 + EP。

        ``catalog.get`` 先做 digest 校验（fail-closed）；未知 skill 抛
        ``SkillNotInstalledError``，不删盘、不发 EP。配置变更统一发
        ``assistant.profile.revised`` EP（12 EP 闭集内）。
        """
        spec = self._catalog.get(assistant_id)  # digest 校验 fail-closed
        home = Path(spec.home_path)
        skill_dir = home / "skills" / skill_id
        if not skill_dir.is_dir():
            raise SkillNotInstalledError(f"skill 未安装: {skill_id}")

        shutil.rmtree(skill_dir)

        manifest = load_manifest(home, assistant_id)
        new_revision_seq = _revision_of(manifest) + 1
        new_manifest = build_manifest(
            assistant_id=assistant_id,
            template_id=str(manifest.get("template_id") or DEFAULT_TEMPLATE_ID),
            revision_seq=new_revision_seq,
            home=home,
            created_at=str(manifest.get("created_at") or "") or None,
        )
        skills_section = manifest.get("skills")
        section: dict[str, Any] = dict(skills_section) if isinstance(skills_section, dict) else {}
        section.pop(skill_id, None)
        new_manifest["skills"] = section
        write_manifest(home, new_manifest)
        # I-B6: 删除技能是配置面变更，必须留 revisions/ 快照供回滚/审计。
        write_revision_snapshot(home, new_revision_seq, new_manifest)

        self._emit_profile_revised(
            AssistantProfileRevisedEventPayload(
                assistant_id=assistant_id,
                revision_seq=new_revision_seq,
                manifest_digest=str(new_manifest["manifest_digest"]),
                actor=actor,
                reason=f"remove_skill:{skill_id}",
                changes=(f"skills/{skill_id}",),
            )
        )

    async def edit(
        self,
        assistant_id: str,
        skill_id: str,
        skill_md: str,
        *,
        actor: str = "system",
    ) -> SkillInstallReceipt:
        """编辑已安装 skill（ADR-0243 PR-3）：COW + 覆盖落盘 + manifest 修订 + EP。

        ``global_link`` 包在此被断链复制为 ``local``（新文件新 inode），
        全局库与其他 agent 零感知（I-B15）。新 SKILL.md 走 0048 结构校验
        与 0067 三闸；失败不写盘、不发 EP。
        """
        spec = self._catalog.get(assistant_id)  # digest 校验 fail-closed
        home = Path(spec.home_path)
        skills_root = home / "skills"
        skill_dir = skills_root / sanitize_skill_id(skill_id)
        if not skill_dir.is_dir():
            raise SkillNotInstalledError(f"skill 未安装: assistant={assistant_id!r} skill={skill_id!r}")

        staging_root = skills_root / _STAGING_DIR_NAME / uuid.uuid4().hex
        try:
            package = self._stage_edited_package(staging_root, skill_dir, skill_id, skill_md)
            artifact = _gate_package(package)
            dest = _place_package(staging_root, skills_root, skill_id)
            _mark_local(dest)

            manifest = load_manifest(home, assistant_id)
            new_revision_seq = _revision_of(manifest) + 1
            package_digest = _package_digest(package)
            extra: dict[str, str] = {}
            previous_digests = manifest.get("digests")
            if isinstance(previous_digests, dict):
                extra = {
                    str(name): str(value)
                    for name, value in previous_digests.items()
                    if isinstance(value, str) and str(name).startswith(_SKILLS_DIGEST_PREFIX)
                }
            extra[f"{_SKILLS_DIGEST_PREFIX}{skill_id}"] = package_digest
            new_manifest = build_manifest(
                assistant_id=assistant_id,
                template_id=str(manifest.get("template_id") or DEFAULT_TEMPLATE_ID),
                revision_seq=new_revision_seq,
                home=home,
                created_at=str(manifest.get("created_at") or "") or None,
                extra_digests=extra,
            )
            skills_section = manifest.get("skills")
            section: dict[str, Any] = (
                dict(skills_section) if isinstance(skills_section, dict) else {}
            )
            section[skill_id] = {
                "digest": package_digest,
                "artifact_state": artifact.state.value,
                "version": package.version,
                "source": "local",
                "installed_at": utc_now_iso(),
                "actor": actor,
            }
            new_manifest["skills"] = section
            write_manifest(home, new_manifest)
            write_revision_snapshot(home, new_revision_seq, new_manifest)
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
            staging_parent = skills_root / _STAGING_DIR_NAME
            if staging_parent.is_dir():
                with contextlib.suppress(OSError):
                    staging_parent.rmdir()

        self._emit_profile_revised(
            AssistantProfileRevisedEventPayload(
                assistant_id=assistant_id,
                revision_seq=new_revision_seq,
                manifest_digest=str(new_manifest["manifest_digest"]),
                actor=actor,
                reason=f"edit_skill:{skill_id}",
                changes=(f"skills/{skill_id}",),
            )
        )
        return SkillInstallReceipt(
            assistant_id=assistant_id,
            skill_id=skill_id,
            version=package.version,
            digest=package_digest,
            artifact_state=artifact.state.value,
            installed_at=utc_now_iso(),
            revision_seq=new_revision_seq,
            manifest_digest=str(new_manifest["manifest_digest"]),
            actor=actor,
            source="local",
            install_path=str(dest),
        )

    def relink_global_skills(
        self,
        assistant_id: str,
        *,
        actor: str = "system",
    ) -> SkillRelinkReport:
        """把 ``global_link`` 技能重链到全局库当前版本（ADR-0243 D1 显式升级）。

        全局更新只写新版本、不动已链接 inode，所以升级必须是显式动作。全部候选
        先在 staging 内成包并过 0067 三闸，再落盘、再整批一次 manifest 修订：
        成包阶段任何失败都不改 ``skills/`` 一个字节。``local`` / install 源条目与
        全局已缺失或已退役的包一律不动（版本固定；删除授权只在 ``remove``）。
        """
        spec = self._catalog.get(assistant_id)  # 配置面 digest 不一致时自愈 reimport,不阻断
        home = Path(spec.home_path)
        skills_root = home / "skills"
        manifest = load_manifest(home, assistant_id)
        skills_section = manifest.get("skills")
        section: Mapping[str, Any] = skills_section if isinstance(skills_section, dict) else {}

        candidates: list[str] = []
        skipped_local: list[str] = []
        for skill_id in sorted(section):
            if _is_global_link(section[skill_id]):
                candidates.append(skill_id)
            else:
                skipped_local.append(skill_id)
        if not candidates:
            return SkillRelinkReport(
                assistant_id=assistant_id,
                revision_seq=_revision_of(manifest),
                manifest_digest=str(manifest.get("manifest_digest") or ""),
                skipped_local=tuple(skipped_local),
            )

        global_store = self._global_store_factory()
        raw_root = getattr(global_store, "root", None)
        if raw_root is None:
            raise TypeError(
                f"全局技能库不支持硬链接 re-link（缺 root 属性）: {type(global_store).__name__}"
            )
        global_root = Path(raw_root)
        home_store = DiskSkillPackageStore(SkillSettings(cache_dir=skills_root))

        already_current: list[str] = []
        skipped_missing_global: list[str] = []
        staged: list[tuple[str, SkillPackage, CapabilityArtifact]] = []
        installed_at = utc_now_iso()  # 整批同一时刻:manifest 条目与 EP 必须一致
        staging_root = skills_root / _STAGING_DIR_NAME / f"relink-{uuid.uuid4().hex}"
        try:
            for skill_id in candidates:
                try:
                    package = global_store.get(skill_id)
                except SkillNotFoundError:
                    skipped_missing_global.append(skill_id)
                    continue
                if package.retired:
                    skipped_missing_global.append(skill_id)
                    continue
                try:
                    current = _package_digest(home_store.get(skill_id))
                except SkillNotFoundError:
                    # 落盘包缺失/不完整 = 未能证明与全局一致 ⇒ 重链把它补齐到
                    # 全局当前版本（重跑收敛到同一终态）。
                    current = ""
                if current == _package_digest(package):
                    already_current.append(skill_id)
                    continue
                staged.append((skill_id, package, _gate_package(package)))
                _link_global_package(global_root, staging_root, skill_id)

            for skill_id, _, _ in staged:
                _place_package(staging_root, skills_root, skill_id)
            if staged:
                manifest = self._record_relink(
                    home=home,
                    assistant_id=assistant_id,
                    relinked=staged,
                    actor=actor,
                    installed_at=installed_at,
                )
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)
            staging_parent = skills_root / _STAGING_DIR_NAME
            if staging_parent.is_dir():
                with contextlib.suppress(OSError):
                    staging_parent.rmdir()  # 仅当空目录时收掉,不留空壳

        revision_seq = _revision_of(manifest)
        manifest_digest = str(manifest["manifest_digest"])
        for skill_id, package, artifact in staged:
            self._emit_installed(
                AssistantSkillInstalledEventPayload(
                    assistant_id=assistant_id,
                    revision_seq=revision_seq,
                    manifest_digest=manifest_digest,
                    actor=actor,
                    skill_id=skill_id,
                    skill_digest=_package_digest(package),
                    artifact_state=artifact.state.value,
                    source=_GLOBAL_LINK_SOURCE,
                    version=package.version,
                    installed_at=installed_at,
                )
            )
        return SkillRelinkReport(
            assistant_id=assistant_id,
            revision_seq=revision_seq,
            manifest_digest=manifest_digest,
            relinked=tuple(skill_id for skill_id, _, _ in staged),
            already_current=tuple(already_current),
            skipped_local=tuple(skipped_local),
            skipped_missing_global=tuple(skipped_missing_global),
        )

    def _stage_edited_package(
        self,
        staging_root: Path,
        skill_dir: Path,
        skill_id: str,
        skill_md: str,
    ) -> SkillPackage:
        """在 staging 里用新 SKILL.md + 既有 resources 重建包并经 0048 校验。"""
        staging_dir = staging_root / skill_id
        staging_dir.mkdir(parents=True, exist_ok=True)
        src_resources = skill_dir / "resources"
        if src_resources.is_dir():
            shutil.copytree(src_resources, staging_dir / "resources", dirs_exist_ok=True)
        (staging_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

        resource_files: dict[str, bytes] = {}
        res_dir = staging_dir / "resources"
        if res_dir.is_dir():
            for path in sorted(res_dir.rglob("*")):
                if path.is_file():
                    rel = safe_rel_path(str(path.relative_to(staging_dir)))
                    if rel:
                        resource_files[rel] = path.read_bytes()

        meta: dict[str, Any] = {}
        old_manifest = skill_dir / "manifest.json"
        if old_manifest.is_file():
            try:
                meta = json.loads(old_manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
        store = DiskSkillPackageStore(SkillSettings(cache_dir=staging_root))
        return store.install_package(
            skill_id=skill_id,
            skill_md_text=skill_md,
            resource_files=resource_files,
            source_url=str(meta.get("source_url") or "") or str(skill_dir),
            version=str(meta.get("version") or ""),
        )

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
            "installed_at": utc_now_iso(),
            "actor": actor,
        }
        new_manifest["skills"] = section
        write_manifest(home, new_manifest)
        # I-B6: 一切配置变更留 revisions/ 快照（install 也是配置面变更）。
        write_revision_snapshot(home, _revision_of(new_manifest), new_manifest)
        return new_manifest

    def _record_relink(
        self,
        *,
        home: Path,
        assistant_id: str,
        relinked: Sequence[tuple[str, SkillPackage, CapabilityArtifact]],
        actor: str,
        installed_at: str,
    ) -> dict[str, object]:
        """整批 re-link 记一次修订:单次 ``revision_seq++`` + 单次写盘 + 单份快照。

        逐技能调 ``_record_install`` 会把一次升级动作记成 N 次配置修订（N 份
        ``revisions/`` 快照 + N 次 ``manifest_digest`` 抖动 ⇒ N 次 AgentSpec
        重编译）,所以这里把整批摘要一次性并入同一个 manifest。
        """
        manifest = load_manifest(home, assistant_id)
        previous_digests = manifest.get("digests")
        extra: dict[str, str] = {}
        if isinstance(previous_digests, dict):
            extra = {
                str(name): str(value)
                for name, value in previous_digests.items()
                if isinstance(value, str) and str(name).startswith(_SKILLS_DIGEST_PREFIX)
            }
        skills_section = manifest.get("skills")
        section: dict[str, Any] = dict(skills_section) if isinstance(skills_section, dict) else {}
        for skill_id, package, artifact in relinked:
            package_digest = _package_digest(package)
            extra[f"{_SKILLS_DIGEST_PREFIX}{skill_id}"] = package_digest
            section[skill_id] = {
                "digest": package_digest,
                "artifact_state": artifact.state.value,
                "version": package.version,
                "source": _GLOBAL_LINK_SOURCE,
                "installed_at": installed_at,
                "actor": actor,
            }

        new_revision_seq = _revision_of(manifest) + 1
        new_manifest = build_manifest(
            assistant_id=assistant_id,
            template_id=str(manifest.get("template_id") or DEFAULT_TEMPLATE_ID),
            revision_seq=new_revision_seq,
            home=home,
            created_at=str(manifest.get("created_at") or "") or None,
            extra_digests=extra,
        )
        new_manifest["skills"] = section
        write_manifest(home, new_manifest)
        # I-B6: 配置面变更留 revisions/ 快照（re-link 改的是技能版本，属配置面）。
        write_revision_snapshot(home, new_revision_seq, new_manifest)
        return new_manifest

    def _emit_installed(self, payload: AssistantSkillInstalledEventPayload) -> None:
        """发 ``assistant.skill.installed`` EP;无 emitter 时仅 log(单元测试路径)。"""
        emit_assistant_ep_or_log(self._emit, "assistant.skill_overlay", ASSISTANT_SKILL_INSTALLED, payload.to_dict())

    def _emit_profile_revised(self, payload: AssistantProfileRevisedEventPayload) -> None:
        """发 ``assistant.profile.revised`` EP（删除 skill 的配置变更）；无 emitter 时仅 log。"""
        emit_assistant_ep_or_log(self._emit, "assistant.skill_overlay", ASSISTANT_PROFILE_REVISED, payload.to_dict())

    def _emit_activated(self, payload: AssistantSkillActivatedEventPayload) -> None:
        """发 ``assistant.skill.activated`` EP;无 emitter 时仅 log(单元测试路径)。"""
        emit_assistant_ep_or_log(self._emit, "assistant.skill_overlay", ASSISTANT_SKILL_ACTIVATED, payload.to_dict())


# 用于测试在不接 ctx 时直接构造
AssistantSkillOverlayImpl = _AssistantSkillOverlayImpl
