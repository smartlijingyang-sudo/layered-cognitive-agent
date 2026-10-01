"""Catalog 业务实现：Home CRUD + manifest digest 守门。

``_AssistantCatalogImpl`` 实现 ``AssistantCatalog`` Protocol；``create / get /
list / retire / revise_profile / reimport / restore_revision`` 与技能物化、
继承快照、AgentSpec 构造等内部 helper 集中于此。EP 发射见 ``events``，
SOUL / plan-overlay / manifest 辅助见对应子模块。
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from lca.contracts.atoms.ids.ids import utc_now_iso
from lca.contracts.models.assistant.spec import (
    AssistantBootstrapRefs,
    AssistantSpec,
)
from lca.contracts.models.team.role.team import (
    RoleProfile,
    ToolPermissionManifest,
)
from lca.contracts.protocols.assistant.catalog import (
    AssistantCatalog,
    AssistantHandle,
    AssistantSummary,
    CreateAssistantRequest,
    PlanRevision,
    ProfilePatch,
)
from lca.contracts.protocols.assistant.role_resolver import RoleCard, RoleNotFoundError
from lca.contracts.protocols.journal.spec.spec import AgentSpec
from lca.infrastructure.assistant.io import (
    load_grants,
    read_json,
    sha256_digest,
    write_json,
)
from lca.plugins.assistant.events._events import (
    AssistantBootstrapCompletedEventPayload,
    AssistantCreatedEventPayload,
    AssistantProfileRevisedEventPayload,
)
from lca.plugins.assistant.home._home_layout import (
    DEFAULT_TEMPLATE_ID,
    SOUL_SAFETY_SECTIONS,
    TEMPLATE_REGISTRY,
    AssistantCatalogError,
    AssistantDigestMismatch,
    HomePaths,
    build_manifest,
    cleanup_home,
    compute_digests,
    diff_digests,
    known_template_ids,
    list_children_dirs,
    load_manifest,
    render_default_template,
    render_template,
    write_home_files,
    write_manifest,
    write_revision_snapshot,
)

from .events import _AssistantCatalogEventsMixin
from .manifest import _copy_manifest_extras, _summary_from_home
from .plan_overlay import _load_plan_overlay, _validate_plan_yaml_text
from .soul import (
    _ensure_non_empty_user_md,
    _goals_yaml_from_role_card,
    _merge_soul_defaults,
    _validate_safety_sections_unchanged,
    _validate_soul,
)

log = structlog.get_logger(__name__)


# ── 物化 helpers ────────────────────────────────────────────────────


def _link_tree(src: Path, dst: Path) -> None:
    """把 ``src`` 目录树硬链接镜像到 ``dst``（文件硬链接，目录新建）。"""
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            _link_tree(child, target)
        elif child.is_file():
            os.link(child, target)


def _materialize_global_skills(
    global_store: Any,
    home: Path,
    skill_ids: tuple[str, ...],
    now: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    """把 ``initial_skills`` 里的全局技能硬链接物化到 ``{home}/skills/``。

    返回 ``(skills 索引, skills digest 前缀)`` 供 Home manifest 写入。每个
    落盘包的 ``manifest.json`` 标记 ``source: "global_link"``（ADR-0243 D2）。
    """
    store_root = getattr(global_store, "root", None)
    if store_root is None:
        raise _CatalogConfigError("全局技能库不支持硬链接物化（缺 root 属性）")
    skills_root = home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    index: dict[str, Any] = {}
    digests: dict[str, str] = {}
    for skill_id in skill_ids:
        src = Path(store_root) / skill_id
        if not (src / "SKILL.md").is_file() or not (src / "manifest.json").is_file():
            raise _CatalogConfigError(f"全局技能不存在: {skill_id}")
        dest = skills_root / skill_id
        if dest.exists():
            shutil.rmtree(dest)
        _link_tree(src, dest)
        # 标记来源：global_link（本地 manifest 多一个 source 字段）
        meta = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
        meta["source"] = "global_link"
        (dest / "manifest.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        digest = sha256_digest(dest / "SKILL.md")
        index[skill_id] = {
            "digest": digest,
            "artifact_state": "verified",
            "version": str(meta.get("version") or ""),
            "source": "global_link",
            "installed_at": now,
            "actor": "system",
        }
        digests[f"skills/{skill_id}"] = digest
    return index, digests


def _list_materializable_global_skills(global_store: Any) -> tuple[str, ...]:
    """返回全局库中可物化（含 SKILL.md + manifest.json）的 skill_id 列表。"""
    store_root = getattr(global_store, "root", None)
    if store_root is None:
        return ()
    return tuple(
        entry.skill_id
        for entry in global_store.list_installed()
        if (Path(store_root) / entry.skill_id / "SKILL.md").is_file()
        and (Path(store_root) / entry.skill_id / "manifest.json").is_file()
    )


def _materialize_default_tools(home: Path, names: tuple[str, ...]) -> None:
    """把平台默认工具名写入 ``{home}/tools.yaml`` 的 ``allow`` 列表。

    保留模板 ``deny`` 与结构，仅把 ``allow`` 替换为去重排序后的工具名；
    ``notes`` 改为创建时物化说明，使 Home 工具配置与 skills/ 对等显式可见
    （ADR-0243 D3 延伸）。tools.yaml 在 ``CONFIG_FACE_FILES`` 内，
    manifest digest 由 ``build_manifest`` / ``compute_digests`` 自动覆盖。
    """
    path = home / "tools.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    tools = data.get("tools")
    if not isinstance(tools, dict):
        tools = {}
        data["tools"] = tools
    tools["allow"] = sorted(set(names))
    tools.setdefault("deny", [])
    data["notes"] = (
        "创建时物化的平台默认工具集（与 skills/ 物化对等）；deny 逐个排除；"
        "需授权工具由 grants.yaml 决定（C5 衰减）。收紧策略可经 revise_profile 修改。"
    )
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# ── 局部异常 ─────────────────────────────────────────────────────────


class _DigestMismatch(AssistantDigestMismatch):
    """带 home 路径的 digest 不匹配异常。"""

    def __init__(
        self,
        home: Path,
        assistant_id: str,
        mismatches: list[str],
    ) -> None:
        super().__init__(
            f"assistant_id={assistant_id!r} 配置面 digest 不匹配 "
            f"(home={home},失败字段={mismatches});走 Catalog.reimport 收编后再 get"
        )
        self.home = home
        self.assistant_id = assistant_id
        self.mismatches = mismatches


class _CatalogConfigError(AssistantCatalogError):
    """PR-3 范围对 template_id 等做硬限;非 AssistantDigestMismatch/AlreadyExists。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ── 通用 helpers ─────────────────────────────────────────────────────


def _new_assistant_id() -> str:
    """生成 ``asst_<12hex>`` 形式的助理 id(与仓内 ``new_id`` 命名一致)。"""
    return f"asst_{uuid.uuid4().hex[:12]}"


def _iso_now(clock: Callable[[], datetime] | None = None) -> str:
    """ISO-8601 UTC 时间字符串。

    生产路径直接返回共享 seam ``utc_now_iso()``（``%Y-%m-%dT%H:%M:%SZ``）；
    ``clock`` 仅为测试注入固定时钟保留的可调用缝（None = 走 seam）。
    """
    if clock is None:
        return utc_now_iso()
    return clock().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── AgentSpec 构造 ────────────────────────────────────────────────────


class _PlaceholderLLM:
    """占位 LLM adapter;运行时 RuntimeFactory 注入真 LLM resolver。"""

    async def complete(self, _prompt: str, **_kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError("占位 LLM;RuntimeFactory 注入真 LLM")

    async def stream(self, _prompt: str, **_kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError("占位 LLM;RuntimeFactory 注入真 LLM")


def _build_agent_spec(home_path: str) -> AgentSpec:
    """从 AssistantHome 构造 AgentSpec：RoleProfile 来自 persona 解析。

    LLM adapter 仍为占位（运行时由 RuntimeFactory 注入）。
    RoleProfile 使用真实数据：name → role, description → goal, SOUL → backstory。
    """
    from lca.plugins.assistant.persona.persona import persona_from_home

    persona = persona_from_home(home_path)
    return AgentSpec(
        profile=RoleProfile(
            role=persona.role or "assistant",
            goal=persona.goal or "be helpful",
            backstory=persona.backstory or "",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        ),
        llm=_PlaceholderLLM(),  # type: ignore[arg-type]
    )


# ── Catalog 实现 ──────────────────────────────────────────────────────


class _AssistantCatalogImpl(_AssistantCatalogEventsMixin, AssistantCatalog):
    """Catalog 内部实现;通过 plugin ``setup`` 注入 ctx。

    单一职责:Home CRUD + manifest digest 守门。``revise_profile`` /
    ``reimport`` 是配置面唯一写入口(ADR-0242 D6);``retire`` 仍为
    COMPAT 占位(delete-when 2026-12-31)。
    """

    def __init__(
        self,
        *,
        root: Path,
        event_emitter: Callable[[str, Mapping[str, Any]], Any] | None = None,
        role_resolver: Any | None = None,
        global_skills_store: Any | None = None,
    ) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._emit = event_emitter
        self._role_resolver = role_resolver
        self._global_skills_store = global_skills_store

    # ── 公开面 ────────────────────────────────────────────────────────

    def create(self, req: CreateAssistantRequest) -> AssistantHandle:
        """物化 Home + manifest;发 ``assistant.created`` EP。

        template_id 必须已登记进 ``_home_layout.TEMPLATE_REGISTRY``
        （ADR-0187 §3 D11/D12 的角色模板面）;未知值抛
        ``_CatalogConfigError``（REST 层映射 400,不回落 default）。

        SOUL 取数顺序（ADR-0242 D1）:``soul`` > ``use_template_soul`` 时的模板
        SOUL > ``from_role`` backstory > 模板默认。``soul`` 非空时必须通过完整度校验（I-B2 fail-closed）,
        缺段 / 长度不足抛 ``SoulValidationError``,不降级用模板 SOUL 创建。

        引导式创建（``seed_user_md`` 或 ``soul`` 非空）:写 USER.md、
        删除 BOOTSTRAP.md 并补发 ``assistant.bootstrap.completed`` EP
        （ADR-0187 §3 D12 完成流;BOOTSTRAP 不在配置面 digest 内,
        删除不影响 manifest）。裸创建（两者皆空）保留 BOOTSTRAP.md。

        技能物化（ADR-0243 D1 / I-B14）:``initial_skills`` 空 = 默认把
        全局技能库全部可物化技能硬链接到 ``{home}/skills/``（全局库不可用时
        保持空技能集）;显式传列表 = 只装指定技能。
        """
        if req.template_id not in TEMPLATE_REGISTRY:
            raise _CatalogConfigError(
                f"未知 template_id={req.template_id!r};已登记: {', '.join(known_template_ids())}"
            )

        assistant_id = _new_assistant_id()
        home = HomePaths(root=self._root / assistant_id)
        if home.root.exists():
            raise _CatalogConfigError(f"assistant home 已存在: {home.root}")

        # 1. 物化文件(失败 ⇒ 半成品 Home 清理)
        rendered = render_template(req.template_id, name=req.name, description=req.description)

        # 1b. soul:向导对齐结果优先,且必须先通过完整度校验
        if req.soul:
            _validate_soul(req.soul)
            # 用户 soul 只含四个核心段;模板预置的默认段在此补上(ADR-0242 附录 C)
            rendered.files["SOUL.md"] = _merge_soul_defaults(req.soul, rendered.files["SOUL.md"])

        # 1c. from_role:卡片填充 emoji / role_id / goals。
        # SOUL 只用 backstory：没有对齐结果，且调用方没有要求留下模板人格。
        card: RoleCard | None = None
        if req.from_role:
            if self._role_resolver is None:
                raise _CatalogConfigError(
                    "from_role 需要 RoleCardResolver；当前 profile 未配置 assistant.role_resolver"
                )
            try:
                card = self._role_resolver.resolve(req.from_role)
            except RoleNotFoundError as exc:
                raise AssistantCatalogError(str(exc)) from exc
            if not req.soul and not req.use_template_soul:
                rendered.files["SOUL.md"] = card.backstory
            profile = json.loads(rendered.files["profile.json"])
            if card.emoji:
                profile["emoji"] = card.emoji
            profile["role_id"] = req.from_role
            rendered.files["profile.json"] = json.dumps(profile, ensure_ascii=False, indent=2)
            rendered.files["goals.yaml"] = _goals_yaml_from_role_card(card)

        try:
            write_home_files(home.root, rendered.files)
        except Exception:
            cleanup_home(home.root)
            raise

        # 2..N:后续步骤任一失败 ⇒ 半成品 Home 清理
        try:
            # 2. seed_user_md 覆盖默认 USER.md
            if req.seed_user_md:
                (home.root / "USER.md").write_text(req.seed_user_md, encoding="utf-8")

            # 2b. inherit_from:把来源 Home 的 skills/ + tools/grants 策略复制为快照
            inherited_index: dict[str, Any] = {}
            inherited_digests: dict[str, str] = {}
            if req.inherit_from:
                inherited_index, inherited_digests = self._copy_inherited_snapshot(
                    req.inherit_from, home.root
                )

            # 2b2. 默认工具物化：非继承创建且显式携带默认工具名时，写入 allow 列表，
            #      使 Home 的工具配置与 skills/ 一样显式可见（ADR-0243 D3 延伸）。
            if req.default_tool_names and not req.inherit_from:
                _materialize_default_tools(home.root, req.default_tool_names)

            # 2c. Home 卫生:USER.md 不允许为空(ADR-0242 D2)
            _ensure_non_empty_user_md(home.root)

            # 2d. initial_skills:默认把全局技能硬链接物化为 Home 有效技能集
            #     (ADR-0243 D1 / I-B14)。空 initial_skills = 物化全部全局技能,
            #     使创建后 {home}/skills/ 非空;显式传列表 = 只装指定技能。
            skills_index: dict[str, Any] = dict(inherited_index)
            skills_digests: dict[str, str] = dict(inherited_digests)
            skills_to_materialize = req.initial_skills
            if not skills_to_materialize and self._global_skills_store is not None:
                skills_to_materialize = _list_materializable_global_skills(
                    self._global_skills_store
                )
            if skills_to_materialize:
                if self._global_skills_store is None:
                    raise _CatalogConfigError("initial_skills 需要全局技能库（skills 能力不可用）")
                materialized_index, materialized_digests = _materialize_global_skills(
                    self._global_skills_store,
                    home.root,
                    skills_to_materialize,
                    _iso_now(),
                )
                skills_index.update(materialized_index)
                skills_digests.update(materialized_digests)

            # 3. 引导式创建完成流:删除 BOOTSTRAP.md（EP 在 manifest 写盘后发,
            #    携带事件时刻的 manifest_digest）
            guided = bool(req.seed_user_md or req.soul)
            if guided and home.bootstrap_md.is_file():
                home.bootstrap_md.unlink()

            # 4. manifest.digests + revision_seq=0
            manifest = build_manifest(
                assistant_id=assistant_id,
                template_id=req.template_id,
                revision_seq=0,
                home=home.root,
                extra_digests=skills_digests,
            )
            if req.from_role:
                manifest["role_id"] = req.from_role
            if req.owner_user_id:
                manifest["user_id"] = req.owner_user_id
            if skills_index:
                manifest["skills"] = skills_index
            write_manifest(home.root, manifest)
            # revision 0 = 出生状态基线:让 revisions/ 从创建起就有内容级回滚锚点。
            write_revision_snapshot(home.root, 0, manifest)
        except Exception:
            cleanup_home(home.root)
            raise

        # 5. EP
        manifest_digest = str(manifest["manifest_digest"])
        self._emit_created(
            AssistantCreatedEventPayload(
                assistant_id=assistant_id,
                revision_seq=0,
                manifest_digest=manifest_digest,
                actor="system",
                home_path=str(home.root),
                template_id=req.template_id,
            )
        )
        if guided:
            self._emit_bootstrap_completed(
                AssistantBootstrapCompletedEventPayload(
                    assistant_id=assistant_id,
                    revision_seq=0,
                    manifest_digest=manifest_digest,
                    actor="system",
                    home_path=str(home.root),
                )
            )

        return AssistantHandle(
            assistant_id=assistant_id,
            home_path=str(home.root),
            revision_seq=0,
        )

    def get(self, assistant_id: str) -> AssistantSpec:
        """digest 校验 + 读 Home + 构 AssistantSpec。

        digest 不一致时不再抛 AssistantDigestMismatch 锁死助理，而是按
        ADR-0187 §3 D2 的 revise_reimport 语义自愈：以磁盘现状重算 digest、
        revision_seq++、记 revision 快照（actor="filesystem"），然后继续。
        这是 Terraform refresh 模型——采纳现实为新基线，读路径永不阻断；
        篡改证据保留在 revision 快照链里。写路径（revise_profile）仍保留
        409 乐观并发校验（K8s resourceVersion 模型）。
        """
        home = HomePaths(root=self._root / assistant_id)
        manifest = load_manifest(home.root, assistant_id)

        # digest 校验:重算配置面文件 digest
        actual_digests = compute_digests(home.root)
        declared_digests_raw = manifest.get("digests") or {}
        if not isinstance(declared_digests_raw, dict):
            declared_digests_raw = {}
        declared_digests: dict[str, str] = {
            str(name): str(value)
            for name, value in declared_digests_raw.items()
            if isinstance(value, str)
        }
        mismatches = diff_digests(declared_digests, actual_digests)
        if mismatches:
            # 自愈：用户手改 Home 文件是最自然的操作，不应锁死助理。
            # reimport 以磁盘现状为输入重算 digest 并记快照，之后继续。
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "assistant %s 配置面 digest 不一致(%s)，自动 reimport 自愈",
                assistant_id,
                ",".join(mismatches),
            )
            self.reimport(assistant_id, reason="auto_heal_on_get")
            manifest = load_manifest(home.root, assistant_id)
            declared_digests = {
                str(name): str(value)
                for name, value in (manifest.get("digests") or {}).items()
                if isinstance(value, str)
            }

        bootstrap = AssistantBootstrapRefs(
            soul_digest=declared_digests["SOUL.md"],
            user_digest=declared_digests["USER.md"],
            agents_digest=declared_digests["AGENTS.md"],
        )

        profile = read_json(home.root / "profile.json")
        revision_seq_raw = manifest.get("revision_seq", 0)
        revision_seq = int(revision_seq_raw) if isinstance(revision_seq_raw, (int, str)) else 0
        template_id_raw = manifest.get("template_id", "")
        template_id = str(template_id_raw) if template_id_raw is not None else ""
        return AssistantSpec(
            assistant_id=assistant_id,
            home_path=str(home.root),
            revision_seq=revision_seq,
            template_id=template_id,
            profile_name=str(profile.get("name", "")),
            profile_description=str(profile.get("description", "")),
            agent_spec=_build_agent_spec(str(home.root)),
            bootstrap=bootstrap,
            skill_ids=(),
            job_ids=(),
            grant_digest=sha256_digest(home.root / "grants.yaml"),
            grants=load_grants(home.root),
            tools_policy_digest=sha256_digest(home.root / "tools.yaml"),
            role_id=str(manifest["role_id"]) if manifest.get("role_id") else None,
            profile_opening_message=str(profile.get("opening_message") or ""),
            profile_locale=str(profile.get("locale") or ""),
            profile_model=str(profile.get("model") or ""),
            # runtime 是 JSON object;非 dict 视作未配置,不阻断 resolve。
            profile_runtime=(
                dict(profile["runtime"]) if isinstance(profile.get("runtime"), dict) else {}
            ),
            manifest_digest=str(manifest.get("manifest_digest") or ""),
            plan_overlay=_load_plan_overlay(home.root),
        )

    def list(self, user_id: str | None = None) -> tuple[AssistantSummary, ...]:
        """扫 ``{assistants_root}/*/manifest.json``;digest 不一致的不列。

        失败语义(PR-3 范围):manifest 缺失 / JSON 损坏 / 必填字段缺失
        等结构性错误 → log warning + 跳过(fail-closed 列表不列坏项);
        digest 不匹配 → log warning + 跳过;**不发 EP**(工程 EP 不在 12 EP
        闭集内,需先 ADR 才加)。

        ``user_id`` 非空时只返回 ``manifest.user_id == user_id`` 的 Home
        （ADR-0252 D5 磁盘侧归属过滤）。存量无 ``user_id`` 字段的 Home
        不匹配任何用户（归属迁移见 ADR-0252 §7 开放问题 1）。
        """
        summaries: list[AssistantSummary] = []
        for child in list_children_dirs(self._root):
            if user_id is not None:
                manifest_path = child / "manifest.json"
                if not manifest_path.is_file():
                    continue
                try:
                    manifest = read_json(manifest_path)
                except (OSError, ValueError):
                    continue
                if str(manifest.get("user_id") or "") != user_id:
                    continue
            summary = _summary_from_home(child)
            if summary is not None:
                summaries.append(summary)
        return tuple(summaries)

    # COMPAT(delete-when: 2026-12-31, scope: retire 入口落地后删除)
    def retire(self, assistant_id: str, reason: str) -> None:
        del assistant_id, reason  # PR-3 占位;待 retire 入口落地
        raise NotImplementedError(
            "AssistantCatalog.retire 在 PR-3 范围不实现;待 retire 入口落地后删除本占位"
        )

    def revise_profile(
        self,
        assistant_id: str,
        patch: ProfilePatch,
        *,
        actor: str = "system",
    ) -> PlanRevision:
        """配置面唯一写入口（ADR-0187 §3 D2 + ADR-0242 D6）。

        字段级 patch：应用变更 → digest 重算 → ``revision_seq++`` →
        ``revisions/`` 快照 → 写 manifest → 发 ``assistant.profile.revised`` EP。
        未知 ``extra`` 键 / 空 patch / SOUL 不完整 ⇒ fail-closed。
        """
        home = HomePaths(root=self._root / assistant_id)
        manifest = load_manifest(home.root, assistant_id)
        self._check_digests(home.root, assistant_id, manifest)

        changes: list[str] = []
        profile = read_json(home.root / "profile.json")
        profile_patched = False
        if patch.profile_name is not None:
            profile["name"] = patch.profile_name
            profile_patched = True
        if patch.profile_description is not None:
            profile["description"] = patch.profile_description
            profile_patched = True
        if patch.profile_opening_message is not None:
            profile["opening_message"] = patch.profile_opening_message
            profile_patched = True
        if patch.profile_locale is not None:
            profile["locale"] = patch.profile_locale
            profile_patched = True
        if patch.profile_model is not None:
            profile["model"] = patch.profile_model
            profile_patched = True
        if patch.profile_runtime is not None:
            profile["runtime"] = patch.profile_runtime
            profile_patched = True
        if profile_patched:
            write_json(home.root / "profile.json", profile)
            changes.append("profile.json")

        if patch.soul_md is not None:
            _validate_soul(patch.soul_md)
            # 安全段是平台保底,revise 不允许整体删除:提交里显式给出的以提交为准,
            # 缺失的先从当前文件回填(保留用户已定制文案),仍缺再用模板兜底。
            # agent 路径（工具）额外受限：安全段内容逐字节不可变，红线只读化。
            soul_path = home.root / "SOUL.md"
            current_soul = soul_path.read_text(encoding="utf-8") if soul_path.is_file() else ""
            if actor == "agent":
                _validate_safety_sections_unchanged(current_soul, patch.soul_md)
            merged_soul = _merge_soul_defaults(patch.soul_md, current_soul)
            if any(marker not in merged_soul for marker in SOUL_SAFETY_SECTIONS):
                template_id = str(manifest.get("template_id") or "") or DEFAULT_TEMPLATE_ID
                try:
                    template_soul = render_template(
                        template_id,
                        name=str(profile.get("name") or ""),
                        description=str(profile.get("description") or ""),
                    ).files["SOUL.md"]
                except AssistantCatalogError:
                    # 未登记模板（如 LobeHub 导入遗留）降级到内置默认模板，保底不丢安全段。
                    template_soul = render_default_template(
                        name=str(profile.get("name") or ""),
                        description=str(profile.get("description") or ""),
                    ).files["SOUL.md"]
                merged_soul = _merge_soul_defaults(merged_soul, template_soul)
            soul_path.write_text(merged_soul, encoding="utf-8")
            changes.append("SOUL.md")
        if patch.user_md is not None:
            (home.root / "USER.md").write_text(patch.user_md, encoding="utf-8")
            changes.append("USER.md")
        if patch.agents_md is not None:
            (home.root / "AGENTS.md").write_text(patch.agents_md, encoding="utf-8")
            changes.append("AGENTS.md")
        if patch.goals_yaml is not None:
            (home.root / "goals.yaml").write_text(patch.goals_yaml, encoding="utf-8")
            changes.append("goals.yaml")
        if patch.grants_yaml is not None:
            (home.root / "grants.yaml").write_text(patch.grants_yaml, encoding="utf-8")
            changes.append("grants.yaml")
        if patch.tools_yaml is not None:
            (home.root / "tools.yaml").write_text(patch.tools_yaml, encoding="utf-8")
            changes.append("tools.yaml")
        if patch.plan_yaml is not None:
            _validate_plan_yaml_text(patch.plan_yaml)
            (home.root / "plan.yaml").write_text(patch.plan_yaml, encoding="utf-8")
            changes.append("plan.yaml")
        if patch.identity_md is not None:
            (home.root / "IDENTITY.md").write_text(patch.identity_md, encoding="utf-8")
            changes.append("IDENTITY.md")
        if patch.extra:
            raise _CatalogConfigError(
                f"ProfilePatch 不支持 extra 字段: {', '.join(sorted(patch.extra))}"
            )
        if not changes:
            raise _CatalogConfigError("ProfilePatch 未指定任何变更")

        new_revision_seq = int(manifest.get("revision_seq") or 0) + 1
        new_manifest = build_manifest(
            assistant_id=assistant_id,
            template_id=str(manifest.get("template_id", "")),
            revision_seq=new_revision_seq,
            home=home.root,
            created_at=str(manifest.get("created_at") or ""),
        )
        _copy_manifest_extras(manifest, new_manifest)
        write_revision_snapshot(home.root, new_revision_seq, new_manifest)
        write_manifest(home.root, new_manifest)

        self._emit_profile_revised(
            AssistantProfileRevisedEventPayload(
                assistant_id=assistant_id,
                revision_seq=new_revision_seq,
                manifest_digest=str(new_manifest["manifest_digest"]),
                actor=actor,
                reason="revise_profile",
                changes=tuple(changes),
            )
        )
        return PlanRevision(
            assistant_id=assistant_id,
            revision_seq=new_revision_seq,
            manifest_digest=str(new_manifest["manifest_digest"]),
            actor=actor,
            snapshot_path=str(home.root / "revisions" / f"{new_revision_seq}.json"),
            revised_at=_iso_now(),
        )

    def reimport(self, assistant_id: str, reason: str) -> PlanRevision:
        """裸改恢复模式（ADR-0187 §3 D2）：以磁盘当前内容重算 digest。

        不校验现有 digest（正是恢复路径的用途）；重算后 ``revision_seq++``、
        写 ``revisions/`` 快照与 manifest、发 ``assistant.profile.revised`` EP。
        """
        home = HomePaths(root=self._root / assistant_id)
        manifest = load_manifest(home.root, assistant_id)
        new_revision_seq = int(manifest.get("revision_seq") or 0) + 1
        new_manifest = build_manifest(
            assistant_id=assistant_id,
            template_id=str(manifest.get("template_id", "")),
            revision_seq=new_revision_seq,
            home=home.root,
            created_at=str(manifest.get("created_at") or ""),
        )
        _copy_manifest_extras(manifest, new_manifest)
        write_revision_snapshot(home.root, new_revision_seq, new_manifest)
        write_manifest(home.root, new_manifest)

        self._emit_profile_revised(
            AssistantProfileRevisedEventPayload(
                assistant_id=assistant_id,
                revision_seq=new_revision_seq,
                manifest_digest=str(new_manifest["manifest_digest"]),
                actor="reimport",
                reason=reason,
                changes=tuple(sorted(compute_digests(home.root))),
            )
        )
        return PlanRevision(
            assistant_id=assistant_id,
            revision_seq=new_revision_seq,
            manifest_digest=str(new_manifest["manifest_digest"]),
            actor="reimport",
            snapshot_path=str(home.root / "revisions" / f"{new_revision_seq}.json"),
            revised_at=_iso_now(),
        )

    def restore_revision(self, assistant_id: str, revision_seq: int) -> PlanRevision:
        """内容级回滚：把配置面恢复为历史修订快照（ADR-0242 D6 延伸）。

        读 ``revisions/{seq}.json`` 的 ``files`` 全文写回 Home，再经 ``reimport``
        重算 digest、``revision_seq++``、写新快照并发 EP（actor=reimport，
        reason=rollback-to-{seq}）。恢复路径与 ``reimport`` 同构，不校验现有
        digest（正是恢复路径的用途）。

        失败语义：快照缺失 / 不含 ``files``（历史 digest-only 快照）⇒
        ``AssistantCatalogError``，不写盘。
        """
        home = HomePaths(root=self._root / assistant_id)
        snapshot_path = home.root / "revisions" / f"{revision_seq}.json"
        if not snapshot_path.is_file():
            raise AssistantCatalogError(f"revision {revision_seq} 快照不存在: {assistant_id}")
        try:
            snapshot = read_json(snapshot_path)
        except (OSError, ValueError) as exc:
            raise AssistantCatalogError(
                f"revision {revision_seq} 快照不可读: {snapshot_path}"
            ) from exc
        files = snapshot.get("files")
        if not isinstance(files, dict):
            raise AssistantCatalogError(
                f"revision {revision_seq} 快照不含文件内容（历史 digest-only 快照），无法回滚。"
            )
        for name, content in files.items():
            if not isinstance(name, str) or not isinstance(content, str):
                raise AssistantCatalogError(
                    f"revision {revision_seq} 快照 files 内容异常: {name!r}"
                )
            (home.root / name).write_text(content, encoding="utf-8")
        return self.reimport(assistant_id, reason=f"rollback-to-{revision_seq}")

    # ── 内部 ──────────────────────────────────────────────────────────

    def _check_digests(self, home: Path, assistant_id: str, manifest: Mapping[str, Any]) -> None:
        """重算配置面 digest 并与 manifest 比对（I-A3 fail-closed）。"""
        actual_digests = compute_digests(home)
        declared_raw = manifest.get("digests") or {}
        declared: dict[str, str] = {
            str(name): str(value) for name, value in declared_raw.items() if isinstance(value, str)
        }
        mismatches = diff_digests(declared, actual_digests)
        if mismatches:
            raise _DigestMismatch(home, assistant_id, mismatches)

    def _copy_inherited_snapshot(
        self, source_id: str, dest_home: Path
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """把来源 Home 的 ``skills/`` + ``tools.yaml`` / ``grants.yaml`` 复制为快照。

        返回 ``(skills 索引, skills digest 前缀)``，供 create 写入新 Home
        manifest（否则继承技能在发现层会变成未索引的 draft）。

        - 先经 ``self.get`` 做 digest 校验:来源未知 / digest 不匹配 ⇒
          ``AssistantCatalogError`` 子类(fail-closed,ADR-0242 D1);
        - ``skills/`` 只复制含 ``SKILL.md`` 的已验证技能目录;
        - ``global_link`` 技能用硬链接复制（保持空间效率与来源标记），
          ``local`` 技能用快照复制（ADR-0243 PR-2）;
        - ``tools.yaml`` / ``grants.yaml`` 整文件复制为新 Home 的策略;
        - 复制是快照,新 Home 之后各自演化。
        """
        source_spec = self.get(source_id)
        source_home = Path(source_spec.home_path)

        source_skills = source_home / "skills"
        dest_skills = dest_home / "skills"
        index: dict[str, Any] = {}
        digests: dict[str, str] = {}
        if source_skills.is_dir():
            for child in sorted(source_skills.iterdir()):
                if child.is_dir() and (child / "SKILL.md").is_file():
                    is_global_link = False
                    meta_path = child / "manifest.json"
                    if meta_path.is_file():
                        try:
                            meta = json.loads(meta_path.read_text(encoding="utf-8"))
                            is_global_link = meta.get("source") == "global_link"
                        except (OSError, ValueError):
                            is_global_link = False
                    dest = dest_skills / child.name
                    if is_global_link:
                        shutil.copytree(
                            child,
                            dest,
                            dirs_exist_ok=True,
                            copy_function=os.link,
                        )
                    else:
                        shutil.copytree(child, dest, dirs_exist_ok=True)
                    digest = sha256_digest(dest / "SKILL.md")
                    index[child.name] = {
                        "digest": digest,
                        "artifact_state": "verified",
                        "version": str(meta.get("version") or "") if is_global_link else "",
                        "source": "global_link" if is_global_link else "local",
                        "installed_at": _iso_now(),
                        "actor": "system",
                    }
                    digests[f"skills/{child.name}"] = digest

        for name in ("tools.yaml", "grants.yaml"):
            src = source_home / name
            if src.is_file():
                (dest_home / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return index, digests
