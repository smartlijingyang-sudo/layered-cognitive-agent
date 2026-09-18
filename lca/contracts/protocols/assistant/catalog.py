"""AssistantCatalog Protocol —— 助理域薄 Catalog（ADR-0187 §3 D4）。

门面层只允许暴露 Home CRUD + 配置面修订 + 生命周期切换；install / evolve /
job 各自有独立 Protocol（``AssistantSkillOverlay`` / SkillAcquirer /
``assistant.jobs`` collector），禁止单类同时实现多 Protocol。架构测试守
「**无** God Catalog」（ADR-0187 §6 删除条件）。

Catalog 是助理域 SSOT 的唯一入口：

- create / get / list —— Home CRUD；
- revise_profile —— patch 模式，digest 重算 + ``revision_seq++``；
- reimport —— 裸改恢复模式，把磁盘当前内容收编为新 digest（ADR-0187 §3 D2）；
- retire —— 转入 retired 状态，拒收新 run。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from lca.contracts.models.assistant.spec import AssistantSpec

# ── Catalog 配套 dataclass ────────────────────────────────


@dataclass(frozen=True)
class CreateAssistantRequest:
    """``AssistantCatalog.create`` 入参。

    两种创建路径：

    1. **模板创建**（``from_role=None``）：用 ``template_id`` 对应的模板填充
       SOUL.md 等配置面。向后兼容旧行为。
    2. **角色档案创建**（``from_role=<role_id>``）：从 ``RoleCardResolver``
       解析角色卡片，用卡片 backstory 填充 SOUL.md，emoji/title 从卡片
       frontmatter 取。模板仍提供其他配置面的默认值（grants/tools/AGENTS）。

    ``initial_skills`` 在 Home 物化后由 Catalog 编排 overlay.install 安装。
    """

    name: str
    description: str = ""
    template_id: str = "assistant.default"
    seed_user_md: str | None = None
    from_role: str | None = None
    """角色档案 role_id（如 'engineering/engineering-software-architect'）。
    非空时 SOUL.md 内容来自 RoleCard.backstory，忽略模板中的 SOUL 文案。"""
    soul: str | None = None
    """向导对齐后的最终 SOUL 全文（ADR-0242 D1）。

    非空时覆盖 ``from_role`` backstory 与模板默认，且必须在
    ``catalog.create`` 边界通过完整度校验（四核心语义段 + 去除空白后
    >= 200 字符）。"""
    inherit_from: str | None = None
    """继承快照来源 assistant_id（ADR-0242 D1/D2）。

    非空时把来源 Home 的 ``skills/``（含 SKILL.md 的目录）与
    ``tools.yaml`` / ``grants.yaml`` 策略复制为新 Home 快照；来源未知或
    digest 不匹配则 fail-closed。"""
    initial_skills: tuple[str, ...] = ()
    """创建后立即安装的 skill_id 列表。空 = 不预装。"""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("name 必须为非空助理名")
        if self.from_role is not None and not self.from_role.strip():
            raise ValueError("from_role 必须为非空字符串或 None")
        # 空字符串统一归一化为 None（向导可能传空值占位）
        for field_name in ("soul", "inherit_from"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                object.__setattr__(self, field_name, None)


@dataclass(frozen=True)
class AssistantHandle:
    """create 成功后的最小回执 —— 仅含 id 与初始 revision。"""

    assistant_id: str
    home_path: str
    revision_seq: int


@dataclass(frozen=True)
class AssistantSummary:
    """``list`` 的轻量视图（不解 manifest，不读 SOUL 全文）。"""

    assistant_id: str
    name: str
    status: str  # active / paused / retired
    template_id: str
    revision_seq: int
    home_path: str
    skill_count: int = 0
    job_count: int = 0
    updated_at: str = ""  # ISO-8601；空 = 未知


@dataclass(frozen=True)
class ProfilePatch:
    """``revise_profile`` 的 patch 载荷 —— 仅声明意图，不含 digest 重算。

    字段为 ``None`` 表示不动；空字符串视为「清空字段」（语义由 Catalog 决定）。
    ``profile_opening_message`` / ``profile_locale`` / ``profile_model`` /
    ``profile_runtime`` 是 ADR-0242 D9 的 Home 数据行，与其他 profile 字段
    一样经 ``revise_profile`` 写盘并进 manifest digest。
    """

    profile_name: str | None = None
    profile_description: str | None = None
    profile_opening_message: str | None = None
    """``profile.json.opening_message``（ADR-0242 D9）；None = 不动。"""
    profile_locale: str | None = None
    """``profile.json.locale``（ADR-0242 D9）；None = 不动。"""
    profile_model: str | None = None
    """``profile.json.model``（ADR-0242 D9）；None = 不动。"""
    profile_runtime: dict[str, object] | None = None
    """``profile.json.runtime``（ADR-0242 D9）；None = 不动。"""
    soul_md: str | None = None
    user_md: str | None = None
    agents_md: str | None = None
    goals_yaml: str | None = None
    grants_yaml: str | None = None
    tools_yaml: str | None = None
    plan_yaml: str | None = None
    """``{home}/plan.yaml`` 的原始 YAML 文本（ADR-0242 D10）。

    None = 不动；非 None = 覆盖整个 plan.yaml（须通过 ``PlanOverlay``
    schema 校验，未知字段 fail-closed），digest 重算并 ``revision_seq++``。"""
    skills: tuple[str, ...] | None = None  # skill_ids 覆盖
    routines: tuple[str, ...] | None = None  # job_ids 覆盖
    extra: dict[str, str] = field(default_factory=dict)
    """预留给后续字段；非空时由 Catalog 决定是否接受。"""


@dataclass(frozen=True)
class PlanRevision:
    """``revise_profile`` / ``reimport`` 的不可变回执。

    与 EP payload 共享四个必备字段（ADR-0187 §3 D8）：``assistant_id`` /
    ``revision_seq`` / ``manifest_digest`` / ``actor``。``actor`` 由调用方
    填入；``"reimport"`` 用于裸改恢复模式。
    """

    assistant_id: str
    revision_seq: int
    manifest_digest: str
    actor: str
    snapshot_path: str  # revisions/{revision_seq}.json 路径
    revised_at: str = ""  # ISO-8601；空 = 未知

    def __post_init__(self) -> None:
        if self.revision_seq < 1:
            raise ValueError(f"revision_seq 必须 >= 1，得到 {self.revision_seq!r}")
        if not self.manifest_digest or not self.manifest_digest.strip():
            raise ValueError("manifest_digest 必须为非空 content digest")
        if not self.actor or not self.actor.strip():
            raise ValueError("actor 必须为非空字符串")
        if not self.snapshot_path or not self.snapshot_path.strip():
            raise ValueError("snapshot_path 必须为非空路径")


# ── Catalog Protocol ────────────────────────────────────────


@runtime_checkable
class AssistantCatalog(Protocol):
    """助理域薄 Catalog —— 仅 Home CRUD + 配置面修订 + retire。

    架构约束（ADR-0187 §6 删除条件 + §3 D4）：

    - 单一类不得同时实现本 Protocol 与 ``AssistantSkillOverlay``、Job 收集器
      或 SkillAcquirer；arch test 守住；
    - 不暴露 ``os.environ`` 读取 / 文件系统 mkdir（根路径只来自 Profile 注入）；
    - 不直接编译 AgentSpec / CompiledRunPlan —— resolve 视图返回 ``AssistantSpec``，
      由 RuntimeFactory（ADR-0088）走同一条 Resolve → Compile 管线。
    """

    def create(self, req: CreateAssistantRequest) -> AssistantHandle: ...

    def get(self, assistant_id: str) -> AssistantSpec:
        """按 assistant_id 取 resolve 视图；不存在抛 ValueError。"""
        ...

    def list(self) -> tuple[AssistantSummary, ...]: ...

    def revise_profile(self, assistant_id: str, patch: ProfilePatch) -> PlanRevision:
        """patch 模式：digest 重算 + ``revision_seq++`` + ``revisions/`` 快照 + EP。"""
        ...

    def reimport(self, assistant_id: str, reason: str) -> PlanRevision:
        """裸改恢复模式：以磁盘当前文件为输入重算全部配置面 digest。

        ``actor="reimport"``；``reason`` 写入 EP 元数据。"""
        ...

    def retire(self, assistant_id: str, reason: str) -> None:
        """转入 retired 状态，拒收新 run（EP assistant.retired）。"""
        ...


__all__ = [
    "AssistantCatalog",
    "AssistantHandle",
    "AssistantSummary",
    "CreateAssistantRequest",
    "PlanRevision",
    "ProfilePatch",
]
