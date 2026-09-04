"""AssistantEvolve Protocol —— 助理域技能自进化缝（ADR-0187 §3 D9）。

``assistant.evolve`` 是全局 ``SkillAcquirer`` 缝（``learning.skill_acquirer``，
``lca/plugins/skill/auto_acquire.py``）的**助理域对应物**：同一
``SkillAcquirer`` Protocol、独立 capability、落点 AssistantHome 而非
``~/.lca/skills``。不新开平行进化协议（ADR-0187 §6 删除条件）。

生命周期（D9）：``observe → distill（scope=experiment，默认不落盘到
skills/）→ promote（WriteApproval + 0067 三闸）→ 写 {home}/skills/``。
候选在提升前一律 ``experiment`` 状态，非 ACTIVE（I-A8）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.protocols.think.learning import SkillAcquisitionCandidate

__all__ = [
    "AssistantEvolve",
    "ObservationDigest",
    "SkillAcquisitionCandidate",
    "SkillInstallReceipt",
    "WriteApproval",
]


@dataclass(frozen=True)
class ObservationDigest:
    """``observe`` 的产物：一次运行轨迹观察的元数据摘要。

    只含引用与标识（run id / evidence ref），**不**携带轨迹全文；
    Spine 内容所有权仍在 0167 总线，digest 只做蒸馏输入。
    """

    assistant_id: str
    run_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    observed_at: str  # ISO-8601

    def __post_init__(self) -> None:
        if not self.assistant_id or not self.assistant_id.strip():
            raise ValueError("ObservationDigest.assistant_id 必须为非空字符串")
        if not self.run_ids:
            raise ValueError("ObservationDigest.run_ids 不得为空（observe 需要输入轨迹）")
        for run_id in self.run_ids:
            if not str(run_id).strip():
                raise ValueError("ObservationDigest.run_ids 含空 run_id")


@dataclass(frozen=True)
class WriteApproval:
    """promote 的写审批凭据（人或显式自动策略；无审批 = 拒收）。

    三个字段全部非空；缺失任一 ⇒ ``promote`` fail-closed。
    """

    approved_by: str
    approved_at: str  # ISO-8601
    reason: str

    def __post_init__(self) -> None:
        if not self.approved_by or not self.approved_by.strip():
            raise ValueError("WriteApproval.approved_by 必须为非空字符串")
        if not self.approved_at or not self.approved_at.strip():
            raise ValueError("WriteApproval.approved_at 必须为非空 ISO-8601 时间")
        if not self.reason or not self.reason.strip():
            raise ValueError("WriteApproval.reason 必须为非空字符串")


# COMPAT(delete-when: 2026-12-31, scope: PR-6 skill_overlay 合入后改复用其 SkillInstallReceipt)
@dataclass(frozen=True)
class SkillInstallReceipt:
    """``promote`` 的不可变回执 —— 技能包写入 Home 后的元数据。

    PR-6 ``assistant.skill_overlay`` 合入后本形状改复用 overlay 的回执定义；
    当前为 evolve 专用最小形状（只含元数据，不含 SKILL 全文）。
    """

    assistant_id: str
    candidate_id: str
    skill_name: str
    skill_path: str  # {home}/skills/{skill_name} 目录
    state: str  # ArtifactState 值（promote 成功后 = active）
    approved_by: str
    promoted_at: str  # ISO-8601

    def __post_init__(self) -> None:
        for field_name in (
            "assistant_id",
            "candidate_id",
            "skill_name",
            "skill_path",
            "approved_by",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"SkillInstallReceipt.{field_name} 必须为非空字符串")
        if not self.state.strip():
            raise ValueError("SkillInstallReceipt.state 必须为非空 ArtifactState 值")


@runtime_checkable
class AssistantEvolve(Protocol):
    """助理域技能进化面（capability ``assistant.evolve``）。

    约束（ADR-0187 §3 D9 + §5 I-A8）：

    - distill 产物 ``scope=experiment``，**默认不落盘**到 ``skills/``；
      候选元数据 + 草稿 digest 存 ``{home}/.evolve/pending/``；
    - promote 必须携带 :class:`WriteApproval` 且通过 0067 三闸
      （identity / invariant / experiment），否则拒收；
    - EP payload 只记元数据（id / digest / actor），禁止 SKILL 全文进 spine。
    """

    def observe(self, assistant_id: str, run_ids: tuple[str, ...]) -> ObservationDigest:
        """从 run 轨迹产观察摘要；助理不存在 / digest 不一致 ⇒ fail-closed。"""

    def distill(self, assistant_id: str, digest: ObservationDigest) -> SkillAcquisitionCandidate:
        """蒸馏候选（experiment）；发 ``assistant.skill.evolved.proposed`` EP。"""

    def list_pending(self, assistant_id: str) -> tuple[SkillAcquisitionCandidate, ...]:
        """列当前待提升候选（按 candidate_id 排序）。"""

    def promote(
        self, assistant_id: str, candidate_id: str, approval: WriteApproval
    ) -> SkillInstallReceipt:
        """0067 闸后写 ``{home}/skills/``；发 ``assistant.skill.evolved.promoted`` EP。"""
