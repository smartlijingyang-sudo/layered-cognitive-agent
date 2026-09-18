"""assistant.catalog plugin —— ADR-0187 §7 PR-3。

薄 Catalog 唯一实现:

- ``provides=("assistant.catalog",)``;
- ``create / get / list`` —— Home CRUD(PR-3 范围);
- ``revise_profile / reimport / retire`` —— 仅签名存在;抛
  ``NotImplementedError`` 加 ``COMPAT(delete-when: ...)`` 注释
  (PR-5/7 补完)。

三层真值(ADR-0187 §3 D2):

| 面 | 字段 | 进 manifest digest? |
|---|---|---|
| 配置(SSOT) | profile / SOUL / USER / AGENTS / goals / grants / tools | 是 |
| 记忆 | MEMORY.md / memory/ | 否(I-A13) |
| 工作区 | workspace/ | 否 |

根路径仅经 Profile ``{from_env: LCA_ASSISTANTS_ROOT}`` 注入;**禁止**
本模块读 ``os.environ``。
"""

from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.assistant.spec import (
    AssistantBootstrapRefs,
    AssistantSpec,
)
from lca.contracts.models.team.role.team import (
    RoleProfile,
    ToolPermissionManifest,
)
from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_CREATED,
    ASSISTANT_PROFILE_REVISED,
)
from lca.contracts.protocols.assistant.catalog import (
    AssistantCatalog,
    AssistantHandle,
    AssistantSummary,
    CreateAssistantRequest,
    PlanRevision,
    ProfilePatch,
)
from lca.contracts.protocols.assistant.role_resolver import RoleCard
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.journal.spec.spec import AgentSpec
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.assistant.events._events import (
    AssistantBootstrapCompletedEventPayload,
    AssistantCreatedEventPayload,
    AssistantProfileRevisedEventPayload,
)
from lca.plugins.assistant.home._home_layout import (
    DEFAULT_TEMPLATE_ID,
    SOUL_CORE_SECTIONS,
    TEMPLATE_REGISTRY,
    HomePaths,
    build_manifest,
    cleanup_home,
    compute_digests,
    count_yaml_in,
    diff_digests,
    known_template_ids,
    list_children_dirs,
    load_manifest,
    render_template,
    write_home_files,
    write_manifest,
)

log = structlog.get_logger(__name__)


# ── Plugin 配置 ───────────────────────────────────────────────────────


class Config(BaseModel):
    """Plugin 配置:根路径仅来自 Profile 注入的 ``LCA_ASSISTANTS_ROOT``。

    ``assistants_root`` 字段是 Profile 装配期由 ``{from_env: LCA_ASSISTANTS_ROOT}``
    展开的实际值。profile 缺字段时 resolver 抛错而非 silent 默认(fail-loud)。
    """

    model_config = ConfigDict(extra="forbid")

    assistants_root: str = Field(min_length=1)
    """``{from_env: LCA_ASSISTANTS_ROOT}`` 展开后的根路径。"""


# ── Catalog 实现 ──────────────────────────────────────────────────────


class _AssistantCatalogImpl(AssistantCatalog):
    """Catalog 内部实现;通过 plugin ``setup`` 注入 ctx。

    单一职责:Home CRUD + manifest digest 守门。``revise_profile`` /
    ``reimport`` / ``retire`` 在 PR-5/7 补完;PR-3 仅占位抛
    ``NotImplementedError``。
    """

    def __init__(
        self,
        *,
        root: Path,
        event_emitter: Callable[[str, Mapping[str, Any]], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        role_resolver: Any | None = None,
    ) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._emit = event_emitter
        self._clock = clock or (lambda: datetime.now(UTC))
        self._role_resolver = role_resolver

    # ── 公开面 ────────────────────────────────────────────────────────

    def create(self, req: CreateAssistantRequest) -> AssistantHandle:
        """物化 Home + manifest;发 ``assistant.created`` EP。

        template_id 必须已登记进 ``_home_layout.TEMPLATE_REGISTRY``
        （ADR-0187 §3 D11/D12 的角色模板面）;未知值抛
        ``_CatalogConfigError``（REST 层映射 400,不回落 default）。

        SOUL 取数顺序（ADR-0242 D1）:``soul`` > ``from_role`` backstory
        > 模板默认。``soul`` 非空时必须通过完整度校验（I-B2 fail-closed）,
        缺段 / 长度不足抛 ``SoulValidationError``,不降级用模板 SOUL 创建。

        引导式创建（``seed_user_md`` 或 ``soul`` 非空）:写 USER.md、
        删除 BOOTSTRAP.md 并补发 ``assistant.bootstrap.completed`` EP
        （ADR-0187 §3 D12 完成流;BOOTSTRAP 不在配置面 digest 内,
        删除不影响 manifest）。裸创建（两者皆空）保留 BOOTSTRAP.md。
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
            rendered.files["SOUL.md"] = req.soul

        # 1c. from_role:卡片填充 emoji / role_id / goals;SOUL 只在无 soul 时用 backstory
        card: RoleCard | None = None
        if req.from_role:
            if self._role_resolver is None:
                raise _CatalogConfigError(
                    "from_role 需要 RoleCardResolver；当前 profile 未配置 assistant.role_resolver"
                )
            card = self._role_resolver.resolve(req.from_role)
            if not req.soul:
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
            if req.inherit_from:
                self._copy_inherited_snapshot(req.inherit_from, home.root)

            # 2c. Home 卫生:USER.md 不允许为空(ADR-0242 D2)
            _ensure_non_empty_user_md(home.root)

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
            )
            if req.from_role:
                manifest["role_id"] = req.from_role
            write_manifest(home.root, manifest)
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
        """digest 校验 + 读 Home + 构 AssistantSpec;失败抛 AssistantDigestMismatch。"""
        home = HomePaths(root=self._root / assistant_id)
        manifest = load_manifest(home.root, assistant_id)

        # digest 校验(I-A3 fail-closed):重算配置面文件 digest
        actual_digests = compute_digests(home.root)
        declared_digests_raw = manifest.get("digests") or {}
        if not isinstance(declared_digests_raw, dict):
            raise _DigestMismatch(home.root, assistant_id, [])
        declared_digests: dict[str, str] = {
            str(name): str(value)
            for name, value in declared_digests_raw.items()
            if isinstance(value, str)
        }
        mismatches = diff_digests(declared_digests, actual_digests)
        if mismatches:
            raise _DigestMismatch(home.root, assistant_id, mismatches)

        bootstrap = AssistantBootstrapRefs(
            soul_digest=declared_digests["SOUL.md"],
            user_digest=declared_digests["USER.md"],
            agents_digest=declared_digests["AGENTS.md"],
        )

        profile = _read_json(home.root / "profile.json")
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
            grant_digest=_sha256_digest(home.root / "grants.yaml"),
            tools_policy_digest=_sha256_digest(home.root / "tools.yaml"),
            role_id=str(manifest["role_id"]) if manifest.get("role_id") else None,
            profile_opening_message=str(profile.get("opening_message") or ""),
            profile_locale=str(profile.get("locale") or ""),
        )

    def list(self) -> tuple[AssistantSummary, ...]:
        """扫 ``{assistants_root}/*/manifest.json``;digest 不一致的不列。

        失败语义(PR-3 范围):manifest 缺失 / JSON 损坏 / 必填字段缺失
        等结构性错误 → log warning + 跳过(fail-closed 列表不列坏项);
        digest 不匹配 → log warning + 跳过;**不发 EP**(工程 EP 不在 12 EP
        闭集内,需先 ADR 才加)。
        """
        summaries: list[AssistantSummary] = []
        for child in list_children_dirs(self._root):
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
        profile = _read_json(home.root / "profile.json")
        profile_patched = False
        if patch.profile_name is not None:
            profile["name"] = patch.profile_name
            profile_patched = True
        if patch.profile_description is not None:
            profile["description"] = patch.profile_description
            profile_patched = True
        if profile_patched:
            _write_json(home.root / "profile.json", profile)
            changes.append("profile.json")

        if patch.soul_md is not None:
            _validate_soul(patch.soul_md)
            (home.root / "SOUL.md").write_text(patch.soul_md, encoding="utf-8")
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
        _write_revision_snapshot(home.root, new_revision_seq, new_manifest)
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
            revised_at=_iso_now(self._clock),
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
        _write_revision_snapshot(home.root, new_revision_seq, new_manifest)
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
            revised_at=_iso_now(self._clock),
        )

    # ── 内部 ──────────────────────────────────────────────────────────

    def _emit_created(self, payload: AssistantCreatedEventPayload) -> None:
        """发 ``assistant.created`` EP;无 emitter 时仅 log(PR-3 单元测试路径)。"""
        if self._emit is None:
            log.info(
                "assistant.catalog.ep.no_emitter",
                ep=ASSISTANT_CREATED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_CREATED, payload.to_dict())

    def _emit_bootstrap_completed(self, payload: AssistantBootstrapCompletedEventPayload) -> None:
        """发 ``assistant.bootstrap.completed`` EP;无 emitter 时仅 log。"""
        if self._emit is None:
            log.info(
                "assistant.catalog.ep.no_emitter",
                ep=ASSISTANT_BOOTSTRAP_COMPLETED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_BOOTSTRAP_COMPLETED, payload.to_dict())

    def _emit_profile_revised(self, payload: AssistantProfileRevisedEventPayload) -> None:
        """发 ``assistant.profile.revised`` EP;无 emitter 时仅 log。"""
        if self._emit is None:
            log.info(
                "assistant.catalog.ep.no_emitter",
                ep=ASSISTANT_PROFILE_REVISED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_PROFILE_REVISED, payload.to_dict())

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

    def _copy_inherited_snapshot(self, source_id: str, dest_home: Path) -> None:
        """把来源 Home 的 ``skills/`` + ``tools.yaml`` / ``grants.yaml`` 复制为快照。

        - 先经 ``self.get`` 做 digest 校验:来源未知 / digest 不匹配 ⇒
          ``AssistantCatalogError`` 子类(fail-closed,ADR-0242 D1);
        - ``skills/`` 只复制含 ``SKILL.md`` 的已验证技能目录;
        - ``tools.yaml`` / ``grants.yaml`` 整文件复制为新 Home 的策略;
        - 复制是快照,新 Home 之后各自演化。
        """
        source_spec = self.get(source_id)
        source_home = Path(source_spec.home_path)

        source_skills = source_home / "skills"
        dest_skills = dest_home / "skills"
        if source_skills.is_dir():
            for child in sorted(source_skills.iterdir()):
                if child.is_dir() and (child / "SKILL.md").is_file():
                    shutil.copytree(child, dest_skills / child.name, dirs_exist_ok=True)

        for name in ("tools.yaml", "grants.yaml"):
            src = source_home / name
            if src.is_file():
                (dest_home / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


# ── AgentSpec 构造 ────────────────────────────────────────────────


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


# ── 局部异常别名(让 catalog.py 不直接 import _home_layout 的所有异常)──


from lca.plugins.assistant.home._home_layout import (  # noqa: E402
    AssistantAlreadyExists,
    AssistantCatalogError,
    AssistantDigestMismatch,
    SoulValidationError,
)


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


# ── helpers ──────────────────────────────────────────────────────────


def _new_assistant_id() -> str:
    """生成 ``asst_<12hex>`` 形式的助理 id(与仓内 ``new_id`` 命名一致)。"""
    return f"asst_{uuid.uuid4().hex[:12]}"


_SOUL_MIN_CHARS = 200
"""SOUL 完整度下限(去除全部空白后,中文按字符计;ADR-0242 D1)。"""


def _validate_soul(soul: str) -> None:
    """SOUL 完整度校验(fail-closed;ADR-0242 I-B2)。

    校验项:
    1. 去除空白后长度 >= ``_SOUL_MIN_CHARS``;
    2. 必须包含四个核心语义段标记(身份/性格/能力/语气)。

    失败抛 :class:`SoulValidationError`,消息明确指出缺哪一段 / 长度不足,
    便于向导继续对齐。安全边界/记忆规则/错误处理/红线由模板预置,不要求。
    """
    compact = "".join(soul.split())
    if len(compact) < _SOUL_MIN_CHARS:
        raise SoulValidationError(
            f"SOUL 完整度不足:去除空白后 {len(compact)} 字符,要求 >= {_SOUL_MIN_CHARS} 字符。"
            "请补充身份/性格/能力/语气的具体内容后再创建,不要用模板默认 SOUL 降级。"
        )
    missing = [marker for marker in SOUL_CORE_SECTIONS if marker not in soul]
    if missing:
        raise SoulValidationError(
            "SOUL 缺少语义段: "
            + ", ".join(missing)
            + "。请补全这四个核心段(身份/性格/能力/语气)后重试;"
            "安全边界/记忆规则/错误处理/红线由模板预置,无需手写。"
        )


def _mission_goal_names(backstory: str, limit: int = 3) -> list[str]:
    """从角色卡 backstory 的「核心使命」段提取 ``###`` 标题作为目标名(ADR-0242 D2)。"""
    lines = backstory.splitlines()
    in_mission = False
    goals: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_mission = "核心使命" in stripped
            continue
        if in_mission and stripped.startswith("### "):
            name = stripped[4:].strip()
            if name and len(goals) < limit:
                goals.append(name)
    return goals


def _goals_yaml_from_role_card(card: RoleCard) -> str:
    """把角色卡核心使命的前三个目标写成非空 goals.yaml(ADR-0242 D2)。

    角色卡没有「核心使命」段时,用角色标题兜底保证 goals.yaml 非空。
    """
    goal_names = _mission_goal_names(card.backstory)
    if not goal_names:
        goal_names = [f"{card.title}核心职责"]
    lines = ["goals:"]
    for name in goal_names:
        lines.append(f"  - name: {name}")
        lines.append(f"    description: 来自角色卡「核心使命」的目标,围绕「{name}」持续交付。")
        lines.append("    success_criteria: 完成该目标下的关键交付物并得到用户认可。")
    lines.append("notes: |")
    lines.append("  目标提取自角色卡「核心使命」段;可经 revise_profile 调整。")
    return "\n".join(lines) + "\n"


_DEFAULT_USER_MD = """# USER

助理服务的对象画像。请在向导中或首次对话中补充以下内容:

- **称呼**:用户希望被怎么称呼?
- **服务对象**:用户的主要身份(如:开发者、产品经理、学生)?
- **偏好**:回复风格、常用工具、禁忌话题?
- **上下文**:用户当前项目 / 场景的关键背景?
"""


def _ensure_non_empty_user_md(home: Path) -> None:
    """Home 卫生:USER.md 不允许为空(ADR-0242 D2)。

    模板已提供可填充骨架;本守卫只在文件缺失或空白时写入默认骨架,
    保证向导创建 / 裸创建的 Home 都不含空 USER.md。
    """
    user_md = home / "USER.md"
    if not user_md.is_file() or not user_md.read_text(encoding="utf-8").strip():
        user_md.write_text(_DEFAULT_USER_MD, encoding="utf-8")


def _sha256_digest(path: Path) -> str:
    """manifest 外部字段 digest(grants / tools policy);复用 _home_layout 的实现。"""
    from lca.plugins.assistant.home._home_layout import sha256_digest

    return sha256_digest(path)


def _read_json(path: Path) -> dict[str, object]:
    """读 JSON 文件;非 dict 抛 ValueError。"""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层不是 JSON object")
    return data


def _write_json(path: Path, data: Mapping[str, object]) -> None:
    """写 JSON 文件（UTF-8 + 缩进 + sort_keys）。"""
    path.write_text(
        json.dumps(dict(data), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def _write_revision_snapshot(home: Path, revision_seq: int, manifest: Mapping[str, object]) -> None:
    """把修订后的 manifest 快照写入 ``revisions/{revision_seq}.json``（ADR-0242 D6）。"""
    revisions_dir = home / "revisions"
    revisions_dir.mkdir(parents=True, exist_ok=True)
    (revisions_dir / f"{revision_seq}.json").write_text(
        json.dumps(dict(manifest), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _copy_manifest_extras(source: Mapping[str, object], target: dict[str, object]) -> None:
    """把 manifest 中非 digest 派生字段（role_id / skills 索引等）复制到修订版。"""
    for key in ("role_id", "skills"):
        if key in source:
            target[key] = source[key]


def _iso_now(clock: Callable[[], datetime]) -> str:
    """ISO-8601 UTC 时间字符串（复用注入时钟）。"""
    return clock().strftime("%Y-%m-%dT%H:%M:%SZ")


def _summary_from_home(home_dir: Path) -> AssistantSummary | None:
    """从一个 candidate home dir 构造 AssistantSummary;失败返回 None。"""
    manifest_path = home_dir / "manifest.json"
    if not manifest_path.is_file():
        log.warning("assistant.catalog.list.skip_no_manifest", home=str(home_dir))
        return None
    try:
        manifest = _read_json(manifest_path)
    except (OSError, ValueError) as exc:
        log.warning(
            "assistant.catalog.list.skip_bad_manifest",
            home=str(home_dir),
            error=str(exc),
        )
        return None

    assistant_id = str(manifest.get("assistant_id") or home_dir.name)
    declared_digests_raw = manifest.get("digests") or {}
    if not isinstance(declared_digests_raw, dict):
        log.warning(
            "assistant.catalog.list.skip_bad_digests",
            assistant_id=assistant_id,
            home=str(home_dir),
        )
        return None
    declared_digests: dict[str, str] = {
        name: str(value) for name, value in declared_digests_raw.items() if isinstance(value, str)
    }
    actual_digests = compute_digests(home_dir)
    mismatches = diff_digests(declared_digests, actual_digests)
    if mismatches:
        log.warning(
            "assistant.catalog.list.skip_digest_mismatch",
            assistant_id=assistant_id,
            mismatches=mismatches,
        )
        return None

    profile_path = home_dir / "profile.json"
    profile = _read_json(profile_path) if profile_path.is_file() else {}
    skills_dir = home_dir / "skills"
    return AssistantSummary(
        assistant_id=assistant_id,
        name=str(profile.get("name", assistant_id)),
        status=str(profile.get("status", "active")),
        template_id=_str_or_default(manifest.get("template_id"), DEFAULT_TEMPLATE_ID),
        revision_seq=_int_or_default(manifest.get("revision_seq"), 0),
        home_path=str(home_dir),
        skill_count=sum(1 for _ in skills_dir.iterdir()) if skills_dir.is_dir() else 0,
        job_count=count_yaml_in(home_dir / "routines"),
        updated_at=_str_or_default(manifest.get("created_at"), ""),
    )


def _str_or_default(value: object, default: str) -> str:
    """mypy 兼容的 manifest 字段取值;非字符串回退 default。"""
    return value if isinstance(value, str) else default


def _int_or_default(value: object, default: int) -> int:
    """mypy 兼容的 manifest 字段取值;非数字回退 default。"""
    if isinstance(value, bool):
        return default  # bool 是 int 子类,显式排除
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


# ── Plugin manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.catalog.catalog",
    provides=(ASSISTANT_CATALOG.key,),
    requires=("event.bus", "event_descriptor_registry"),
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.FILESYSTEM,),
    description=(
        "Home CRUD + manifest digest 校验(ADR-0187 §7 PR-3);"
        "不做 install/evolve/job,详见 protocol AssistantCatalog 注释。"
    ),
    test_suite="tests/plugins/assistant/test_catalog.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca.plugins.assistant.catalog.checked",
                "lca.plugins.assistant.catalog.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus", "event_descriptor_registry"),
        emits=(ASSISTANT_CREATED, ASSISTANT_BOOTSTRAP_COMPLETED),
        state_mutation="scoped",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """assistant.catalog plugin boot。

    行为契约:

    1. 取 Profile 注入的 ``assistants_root``(由 ``{from_env: LCA_ASSISTANTS_ROOT}``
       展开),构造 :class:`_AssistantCatalogImpl`;**不**读 ``os.environ``。
    2. 若 ``event_descriptor_registry`` 已登记 ``assistant.*`` EP 描述符,
       跳过(避免重复 register);否则补登 12 个 assistant 描述符(PR-2
       已落 contracts 层冻结元数据,本步骤仅在 registry 缺位时补齐)。
    3. EP 发射走 audited ``ctx.emit``(PluginEventBus.emit),具体 EventBus.publish
       由 lca.events.bus plugin 装配期安装。

    失败语义:``assistants_root`` 不可写 → 立即抛 ProfileResolveError 衍生错误
    由 plugin manager 接住(不静默降级到默认路径)。
    """
    root = Path(config.assistants_root).expanduser()  # noqa: ASYNC240 - setup path resolution, not async file IO

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

    catalog = _AssistantCatalogImpl(
        root=root,
        event_emitter=_emit,
        role_resolver=_try_build_role_resolver(),
    )
    ctx.provide(ASSISTANT_CATALOG.key, catalog)

    # 补登 assistant EP 描述符:PR-2 已落 contracts 层 _ASSISTANT_EVENT_DESCRIPTORS;
    # 若 event_descriptor_registry 已被 lca-event-descriptor-bootstrap 灌入 12 个 EP,
    # 此处 register 会因同名已存在抛错 → 已存在则忽略。
    registry = ctx.soft_get("event_descriptor_registry")
    if registry is not None:
        from contextlib import suppress

        from lca.contracts.observability.closure.assistant_ep_closure import (
            all_assistant_event_descriptors,
        )

        for descriptor in all_assistant_event_descriptors():
            with suppress(ValueError):
                # 已登记(PR-2 bootstrap path);按 PR-2 闭集规则不动现有登记
                registry.register(descriptor, replace=False)


# 用于测试在不接 ctx 时直接构造
AssistantCatalogImpl = _AssistantCatalogImpl


def _try_build_role_resolver() -> Any | None:
    """尝试构造 FileRoleCardResolver；roles/ 不可用则返回 None（不阻断 catalog boot）。"""
    try:
        from lca.infrastructure.tools.assistant.role_card_resolver import FileRoleCardResolver

        return FileRoleCardResolver()
    except Exception:
        return None


__all__ = [
    "AssistantAlreadyExists",
    "AssistantCatalogError",
    "AssistantCatalogImpl",
    "AssistantDigestMismatch",
    "Config",
    "SoulValidationError",
    "setup",
]
