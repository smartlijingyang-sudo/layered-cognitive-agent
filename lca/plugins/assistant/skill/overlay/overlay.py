"""assistant.skill_overlay —— Overlay 实现类。

``_AssistantSkillOverlayImpl`` 承载 install / list_installed / activate /
remove / edit;manifest skills 索引修订与 EP 发射仍在此实现。
"""

from __future__ import annotations

import contextlib
import json
import shutil
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import structlog

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
    SkillSource,
)
from lca.contracts.protocols.memory.operational_skills import SkillImporter, SkillPackage
from lca.infrastructure.skills.disk.store import (
    DiskSkillPackageStore,
    safe_rel_path,
    sanitize_skill_id,
)
from lca.infrastructure.skills.settings.settings import SkillSettings
from lca.plugins.assistant.events._events import (
    AssistantProfileRevisedEventPayload,
    AssistantSkillActivatedEventPayload,
    AssistantSkillInstalledEventPayload,
)
from lca.plugins.assistant.home._home_layout import (
    DEFAULT_TEMPLATE_ID,
    build_manifest,
    load_manifest,
    write_manifest,
    write_revision_snapshot,
)
from lca.plugins.assistant.skill.overlay.gating import (
    _ACTIVATABLE_STATES,
    _SKILLS_DIGEST_PREFIX,
    _STAGING_DIR_NAME,
    _gate_package,
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
    ) -> None:
        self._catalog = catalog
        self._emit = event_emitter
        self._url_importer_factory = url_importer_factory or _default_url_importer

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
        if state not in _ACTIVATABLE_STATES:
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

    def _emit_profile_revised(self, payload: AssistantProfileRevisedEventPayload) -> None:
        """发 ``assistant.profile.revised`` EP（删除 skill 的配置变更）；无 emitter 时仅 log。"""
        if self._emit is None:
            log.info(
                "assistant.skill_overlay.ep.no_emitter",
                ep=ASSISTANT_PROFILE_REVISED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_PROFILE_REVISED, payload.to_dict())

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


# 用于测试在不接 ctx 时直接构造
AssistantSkillOverlayImpl = _AssistantSkillOverlayImpl
