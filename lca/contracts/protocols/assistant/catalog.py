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

    模板 id 钉为 ``assistant.default``（ADR-0187 §3 D11）；初始 skill 由
    Catalog 编排调用 overlay.install，Catalog 自身不实现安装逻辑。
    """

    name: str
    description: str = ""
    template_id: str = "assistant.default"
    seed_user_md: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("name 必须为非空助理名")


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
    """

    profile_name: str | None = None
    profile_description: str | None = None
    soul_md: str | None = None
    identity_md: str | None = None
    user_md: str | None = None
    agents_md: str | None = None
    goals_yaml: str | None = None
    grants_yaml: str | None = None
    tools_yaml: str | None = None
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

    def list(self) -> tuple[AssistantSummary, ...]: ...

    def revise_profile(self, assistant_id: str, patch: ProfilePatch) -> PlanRevision:
        """patch 模式：digest 重算 + ``revision_seq++`` + ``revisions/`` 快照 + EP。"""

    def reimport(self, assistant_id: str, reason: str) -> PlanRevision:
        """裸改恢复模式：以磁盘当前文件为输入重算全部配置面 digest。

        ``actor="reimport"``；``reason`` 写入 EP 元数据。"""

    def retire(self, assistant_id: str, reason: str) -> None:
        """转入 retired 状态，拒收新 run（EP assistant.retired）。"""


__all__ = [
    "AssistantCatalog",
    "AssistantHandle",
    "AssistantSummary",
    "CreateAssistantRequest",
    "PlanRevision",
    "ProfilePatch",
]
