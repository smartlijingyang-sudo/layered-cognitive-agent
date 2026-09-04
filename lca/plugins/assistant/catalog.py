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
| 配置(SSOT) | profile / SOUL / IDENTITY / USER / AGENTS / goals / grants / tools | 是 |
| 记忆 | MEMORY.md / memory/ | 否(I-A13) |
| 工作区 | workspace/ | 否 |

根路径仅经 Profile ``{from_env: LCA_ASSISTANTS_ROOT}`` 注入;**禁止**
本模块读 ``os.environ``。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
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
from lca.contracts.models.team.role_team import (
    RoleProfile,
    ToolPermissionManifest,
)
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_CREATED,
)
from lca.contracts.protocols.assistant.catalog import (
    AssistantCatalog,
    AssistantHandle,
    AssistantSummary,
    CreateAssistantRequest,
    PlanRevision,
    ProfilePatch,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.journal.spec import AgentSpec
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.assistant._events import (
    AssistantBootstrapCompletedEventPayload,
    AssistantCreatedEventPayload,
)
from lca.plugins.assistant._home_layout import (
    DEFAULT_TEMPLATE_ID,
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
    ) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._emit = event_emitter
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    # ── 公开面 ────────────────────────────────────────────────────────

    def create(self, req: CreateAssistantRequest) -> AssistantHandle:
        """物化 Home + manifest;发 ``assistant.created`` EP。

        template_id 必须已登记进 ``_home_layout.TEMPLATE_REGISTRY``
        （ADR-0187 §3 D11/D12 的角色模板面）;未知值抛
        ``_CatalogConfigError``（REST 层映射 400,不回落 default）。

        ``seed_user_md`` 非空 = 引导式创建:覆盖 USER.md 后删除
        BOOTSTRAP.md 并补发 ``assistant.bootstrap.completed`` EP
        （ADR-0187 §3 D12 完成流;BOOTSTRAP 不在配置面 digest 内,
        删除不影响 manifest）。
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

            # 3. 引导式创建完成流:删除 BOOTSTRAP.md（EP 在 manifest 写盘后发,
            #    携带事件时刻的 manifest_digest）
            if req.seed_user_md and home.bootstrap_md.is_file():
                home.bootstrap_md.unlink()

            # 4. manifest.digests + revision_seq=0
            manifest = build_manifest(
                assistant_id=assistant_id,
                template_id=req.template_id,
                revision_seq=0,
                home=home.root,
            )
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
        if req.seed_user_md:
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
            identity_digest=declared_digests["IDENTITY.md"],
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
            agent_spec=_placeholder_agent_spec(
                name=str(profile.get("name", "")),
                description=str(profile.get("description", "")),
            ),
            bootstrap=bootstrap,
            skill_ids=(),
            job_ids=(),
            grant_digest=_sha256_digest(home.root / "grants.yaml"),
            tools_policy_digest=_sha256_digest(home.root / "tools.yaml"),
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

    # COMPAT(delete-when: 2026-12-31, scope: revise_profile / reimport 落实现并补 I-A7 验收)
    def revise_profile(self, assistant_id: str, patch: ProfilePatch) -> PlanRevision:
        del assistant_id, patch  # PR-3 占位;待 ProfilePatch 语义 + I-A7 验收的 PR 落地
        raise NotImplementedError(
            "AssistantCatalog.revise_profile 在 PR-3 范围不实现;待 revise/reimport 落地后删除本占位"
        )

    # COMPAT(delete-when: 2026-12-31, scope: revise_profile / reimport 落实现并补 I-A7 验收)
    def reimport(self, assistant_id: str, reason: str) -> PlanRevision:
        del assistant_id, reason  # PR-3 占位;待裸改恢复路径落地
        raise NotImplementedError(
            "AssistantCatalog.reimport 在 PR-3 范围不实现;待 reimport 路径落地后删除本占位"
        )

    # COMPAT(delete-when: 2026-12-31, scope: retire 入口 + create-assistant skill 落实现)
    def retire(self, assistant_id: str, reason: str) -> None:
        del assistant_id, reason  # PR-3 占位;待 retire 入口落地
        raise NotImplementedError(
            "AssistantCatalog.retire 在 PR-3 范围不实现;待 retire 入口落地后删除本占位"
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


# ── 占位 AgentSpec(PR-3 范围)────────────────────────────────────────


class _PlaceholderLLM:
    """PR-3 占位 LLM adapter;PR-4 RuntimeFactory 注入真 LLM resolver。"""

    async def complete(self, _prompt: str, **_kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError("PR-3 占位 LLM;PR-4 RuntimeFactory 注入真 LLM")

    async def stream(self, _prompt: str, **_kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError("PR-3 占位 LLM;PR-4 RuntimeFactory 注入真 LLM")


def _placeholder_agent_spec(*, name: str, description: str) -> AgentSpec:
    """构造最小可工作的占位 AgentSpec(PR-3 范围)。

    PR-4 才把具体 llm/tools/budget 填实;本 PR 的 ``AssistantSpec.agent_spec``
    仅承载 ``profile`` 字段以满足 dataclass 形状,不参与 resolve 期编译。
    """
    return AgentSpec(
        profile=RoleProfile(
            role="assistant.role",
            goal=description or "be helpful",
            backstory=f"PR-3 占位;assistant={name}",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        ),
        llm=_PlaceholderLLM(),  # type: ignore[arg-type]
    )


# ── 局部异常别名(让 catalog.py 不直接 import _home_layout 的所有异常)──


from lca.plugins.assistant._home_layout import (  # noqa: E402
    AssistantAlreadyExists,
    AssistantCatalogError,
    AssistantDigestMismatch,
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


def _sha256_digest(path: Path) -> str:
    """manifest 外部字段 digest(grants / tools policy);复用 _home_layout 的实现。"""
    from lca.plugins.assistant._home_layout import sha256_digest

    return sha256_digest(path)


def _read_json(path: Path) -> dict[str, object]:
    """读 JSON 文件;非 dict 抛 ValueError。"""
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: 顶层不是 JSON object")
    return data


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
    id="lca.plugins.assistant.catalog",
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
        state_mutation="reducer-only",
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
        # audit event 类型已由 ctx.emit 守门(走 audited PluginEventBus.emit)
        return ctx.emit(event, dict(payload))

    catalog = _AssistantCatalogImpl(root=root, event_emitter=_emit)
    ctx.provide(ASSISTANT_CATALOG.key, catalog)

    # 补登 assistant EP 描述符:PR-2 已落 contracts 层 _ASSISTANT_EVENT_DESCRIPTORS;
    # 若 event_descriptor_registry 已被 lca-event-descriptor-bootstrap 灌入 12 个 EP,
    # 此处 register 会因同名已存在抛错 → 已存在则忽略。
    registry = ctx.soft_get("event_descriptor_registry")
    if registry is not None:
        from contextlib import suppress

        from lca.contracts.observability.assistant_ep_closure import (
            all_assistant_event_descriptors,
        )

        for descriptor in all_assistant_event_descriptors():
            with suppress(ValueError):
                # 已登记(PR-2 bootstrap path);按 PR-2 闭集规则不动现有登记
                registry.register(descriptor, replace=False)


# 用于测试在不接 ctx 时直接构造
AssistantCatalogImpl = _AssistantCatalogImpl

__all__ = [
    "AssistantAlreadyExists",
    "AssistantCatalogError",
    "AssistantCatalogImpl",
    "AssistantDigestMismatch",
    "Config",
    "setup",
]
