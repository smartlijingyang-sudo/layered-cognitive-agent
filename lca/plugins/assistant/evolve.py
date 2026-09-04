"""assistant.evolve plugin —— ADR-0187 §3 D9 + §7 PR-8。

助理域 ``SkillAcquirer`` 实现（capability ``assistant.evolve``）：与全局
``learning.skill_acquirer``（``lca/plugins/skill/auto_acquire.py``）同一
``SkillAcquirer`` Protocol、独立 capability、落点 AssistantHome 而非
``~/.lca/skills``。不新开平行进化协议。

生命周期（D9）：

- ``observe`` —— 从 run 轨迹产 :cls:`ObservationDigest`（仅引用，无全文）；
- ``distill`` —— 产 ``scope=experiment`` 候选，**默认不落盘**到 ``skills/``；
  候选元数据 + 草稿 digest 存 ``{home}/.evolve/pending/``；发
  ``assistant.skill.evolved.proposed`` EP（仅元数据）；
- ``promote`` —— 必带 :cls:`WriteApproval`，经 0067 三闸
  （identity / invariant / experiment）后写 ``{home}/skills/``；发
  ``assistant.skill.evolved.promoted`` EP（仅元数据）。

PR-8 distill 是启发式模板蒸馏；离线 GEPA 类蒸馏 = ADR-0187.2（不做）。
EP payload 禁止 SKILL 全文 / 草稿正文（ADR-0187 §3 D2 末段 + D9）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.artifact_state import ArtifactState, is_legal_transition
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_EVOLVE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.harness.journal.artifact import (
    artifact_with_scope,
    capability_artifact_to_dict,
    make_capability_artifact,
    migrate_to_active,
    migrate_to_verified,
)
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_SKILL_EVOLVED_PROMOTED,
    ASSISTANT_SKILL_EVOLVED_PROPOSED,
)
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.assistant.evolve import (
    AssistantEvolve,
    ObservationDigest,
    SkillInstallReceipt,
    WriteApproval,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.think.learning import (
    SkillAcquirer,
    SkillAcquisitionCandidate,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.assistant._events import (
    AssistantSkillEvolvedPromotedEventPayload,
    AssistantSkillEvolvedProposedEventPayload,
)
from lca.plugins.assistant._home_layout import (
    build_manifest,
    load_manifest,
    write_manifest,
)

log = structlog.get_logger(__name__)


# ── 常量 ─────────────────────────────────────────────────────────────

_EXPERIMENT_SCOPE: str = "experiment"
"""候选提升前一律 experiment 状态（I-A8：默认非 ACTIVE）。"""

_PENDING_DIR: str = ".evolve/pending"
"""提案卡目录（元数据 + 草稿）；不是生产 ``skills/`` 面。"""


# ── 异常 ──────────────────────────────────────────────────────────────


class AssistantEvolveError(RuntimeError):
    """evolve 错误基类（4xx 语义；不静默回落）。"""


class MissingWriteApproval(AssistantEvolveError):  # noqa: N818
    """promote 未携带合法 :cls:`WriteApproval`（fail-closed）。"""


class PromoteGateRejected(AssistantEvolveError):  # noqa: N818
    """0067 三闸（identity / invariant / experiment）拒绝提升。"""


class UnknownCandidate(AssistantEvolveError):  # noqa: N818
    """promote / 查询的 candidate_id 不在 ``{home}/.evolve/pending/``。"""


# ── Plugin 配置 ───────────────────────────────────────────────────────


class Config(BaseModel):
    """evolve 证据门（对齐 auto_acquire 的 gate 语义）。"""

    model_config = ConfigDict(extra="forbid")

    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    min_evidence: int = Field(default=1, ge=1)
    draft_confidence: float = Field(default=0.8, ge=0.0, le=1.0)


# ── 实现 ─────────────────────────────────────────────────────────────


class _AssistantEvolveImpl(AssistantEvolve, SkillAcquirer):
    """evolve 内部实现；通过 plugin ``setup`` 注入 catalog 与 emitter。

    单一职责：候选蒸馏 + 治理提升。Home 真值读取经 ``catalog.get``
    （digest 校验由 catalog 守门）；本类不重算配置面 digest。
    """

    def __init__(
        self,
        *,
        catalog: AssistantCatalog,
        event_emitter: Callable[[str, Mapping[str, Any]], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
        min_confidence: float = 0.7,
        min_evidence: int = 1,
        draft_confidence: float = 0.8,
    ) -> None:
        self._catalog = catalog
        self._emit_fn = event_emitter
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._min_confidence = min_confidence
        self._min_evidence = min_evidence
        self._draft_confidence = draft_confidence

    # ── SkillAcquirer 缝（同一 Protocol，独立 capability）────────────

    def propose(
        self,
        *,
        task_ref: str,
        procedure: str,
        success: bool,
        confidence: float,
        evidence_refs: tuple[str, ...],
    ) -> SkillAcquisitionCandidate | None:
        """产证据门候选；不满足门限返回 ``None``，不改任何 skill store。

        与 ``AutoAcquireSkillService.propose`` 同语义；候选 ``status`` 钉为
        ``experiment``（全局缝默认 ``draft``，助理域闭集用 experiment）。
        """
        if (
            not success
            or not task_ref.strip()
            or not procedure.strip()
            or confidence < self._min_confidence
            or len(evidence_refs) < self._min_evidence
        ):
            return None
        digest = _content_digest(f"{task_ref}\0{procedure}\0{'|'.join(evidence_refs)}")[:16]
        return SkillAcquisitionCandidate(
            candidate_id=f"asst-skill-candidate-{digest}",
            task_ref=task_ref,
            procedure=procedure,
            confidence=confidence,
            evidence_refs=tuple(evidence_refs),
            status=_EXPERIMENT_SCOPE,
        )

    # ── AssistantEvolve 面 ───────────────────────────────────────────

    def observe(self, assistant_id: str, run_ids: tuple[str, ...]) -> ObservationDigest:
        """从 run 轨迹产观察摘要；助理缺失 / digest 不一致 ⇒ catalog 抛错。"""
        if not run_ids:
            raise ValueError("observe 需要至少一个 run_id")
        self._catalog.get(assistant_id)  # digest 校验（I-A3 fail-closed）
        evidence = tuple(f"spine:{run_id}" for run_id in run_ids)
        return ObservationDigest(
            assistant_id=assistant_id,
            run_ids=tuple(run_ids),
            evidence_refs=evidence,
            observed_at=_iso(self._clock()),
        )

    def distill(self, assistant_id: str, digest: ObservationDigest) -> SkillAcquisitionCandidate:
        """蒸馏 experiment 候选；落提案卡（不落 ``skills/``）；发 proposed EP。"""
        spec = self._catalog.get(assistant_id)
        home = Path(spec.home_path)
        manifest_digest = str(load_manifest(home, assistant_id)["manifest_digest"])
        task_ref = f"assistant:{assistant_id}:runs:{','.join(digest.run_ids)}"
        candidate = self.propose(
            task_ref=task_ref,
            procedure=_draft_procedure(assistant_id=assistant_id, task_ref=task_ref, digest=digest),
            success=True,
            confidence=self._draft_confidence,
            evidence_refs=digest.evidence_refs,
        )
        if candidate is None:
            raise AssistantEvolveError(
                f"assistant={assistant_id!r} 证据门拒绝候选"
                f"(min_confidence={self._min_confidence}, min_evidence={self._min_evidence})"
            )
        draft_digest = self._write_pending_card(
            home,
            assistant_id=assistant_id,
            revision_seq=spec.revision_seq,
            manifest_digest=manifest_digest,
            candidate=candidate,
        )
        self._emit(
            ASSISTANT_SKILL_EVOLVED_PROPOSED,
            AssistantSkillEvolvedProposedEventPayload(
                assistant_id=assistant_id,
                revision_seq=spec.revision_seq,
                manifest_digest=manifest_digest,
                actor="assistant.evolve",
                candidate_id=candidate.candidate_id,
                skill_name=_skill_name(candidate.candidate_id),
                draft_digest=draft_digest,
            ).to_dict(),
        )
        return candidate

    def list_pending(self, assistant_id: str) -> tuple[SkillAcquisitionCandidate, ...]:
        """读 ``{home}/.evolve/pending/*.json`` 重建候选（按 candidate_id 排序）。"""
        spec = self._catalog.get(assistant_id)
        pending_dir = Path(spec.home_path) / _PENDING_DIR
        if not pending_dir.is_dir():
            return ()
        candidates: list[SkillAcquisitionCandidate] = []
        for card_path in sorted(pending_dir.glob("*.json")):
            card = _read_card(card_path)
            draft_path = card_path.with_suffix(".md")
            procedure = draft_path.read_text(encoding="utf-8") if draft_path.is_file() else ""
            candidates.append(
                SkillAcquisitionCandidate(
                    candidate_id=str(card["candidate_id"]),
                    task_ref=str(card.get("task_ref", "")),
                    procedure=procedure,
                    confidence=float(card.get("confidence", 0.0)),
                    evidence_refs=tuple(str(ref) for ref in card.get("evidence_refs", ())),
                    status=str(card.get("status", _EXPERIMENT_SCOPE)),
                )
            )
        return tuple(sorted(candidates, key=lambda c: c.candidate_id))

    def promote(
        self, assistant_id: str, candidate_id: str, approval: WriteApproval
    ) -> SkillInstallReceipt:
        """0067 三闸 + ``WriteApproval`` 后写 ``{home}/skills/``；发 promoted EP。

        失败语义：无审批 / 审批非法 ⇒ :cls:`MissingWriteApproval`；
        三闸任一拒绝 ⇒ :cls:`PromoteGateRejected`；候选不存在 ⇒
        :cls:`UnknownCandidate`。全部 fail-closed，不部分写盘。
        """
        if not isinstance(approval, WriteApproval):
            raise MissingWriteApproval(
                f"promote 必须携带 WriteApproval,得到 {type(approval).__name__}"
            )
        spec = self._catalog.get(assistant_id)
        home = Path(spec.home_path)
        card_path = home / _PENDING_DIR / f"{candidate_id}.json"
        if not card_path.is_file():
            raise UnknownCandidate(f"candidate_id={candidate_id!r} 不在 {home / _PENDING_DIR}")
        card = _read_card(card_path)
        draft_path = card_path.with_suffix(".md")
        draft_md = draft_path.read_text(encoding="utf-8") if draft_path.is_file() else ""

        # 0067 三闸（identity / invariant / experiment）
        self._gate_identity(card, assistant_id)
        self._gate_invariant(card, home, draft_md)
        self._gate_experiment(card)

        # 0067 状态机：DRAFT → VERIFIED（闸通过）→ 写盘 → ACTIVE（提升完成）
        artifact = make_capability_artifact(
            logical_id=candidate_id,
            content=draft_md,
            scope=Scope.EXPERIMENT,
            state=ArtifactState.DRAFT,
            metadata={"assistant_id": assistant_id, "skill_name": str(card["skill_name"])},
        )
        artifact = migrate_to_verified(artifact)
        skill_name = str(card["skill_name"])
        skill_dir = home / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=False)
        (skill_dir / "SKILL.md").write_text(draft_md, encoding="utf-8")
        artifact = artifact_with_scope(artifact, Scope.AGENT)
        artifact = migrate_to_active(artifact)
        install_meta = capability_artifact_to_dict(artifact)
        install_meta.update(
            {
                "candidate_id": candidate_id,
                "approved_by": approval.approved_by,
                "approved_at": approval.approved_at,
                "reason": approval.reason,
                "promoted_at": _iso(self._clock()),
            }
        )
        (skill_dir / "install.json").write_text(
            json.dumps(install_meta, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # COMPAT(delete-when: 2026-12-31, scope: catalog.revise_profile 落实现后, manifest revision_seq++ 改经 revise 入口, evolve 不再直写 manifest)
        manifest = load_manifest(home, assistant_id)
        current_seq_raw = manifest.get("revision_seq", 0)
        new_revision_seq = (int(current_seq_raw) if isinstance(current_seq_raw, int) else 0) + 1
        new_manifest = build_manifest(
            assistant_id=assistant_id,
            template_id=str(manifest.get("template_id", "")),
            revision_seq=new_revision_seq,
            home=home,
        )
        write_manifest(home, new_manifest)

        card_path.unlink()
        if draft_path.is_file():
            draft_path.unlink()

        promoted_at = _iso(self._clock())
        self._emit(
            ASSISTANT_SKILL_EVOLVED_PROMOTED,
            AssistantSkillEvolvedPromotedEventPayload(
                assistant_id=assistant_id,
                revision_seq=new_revision_seq,
                manifest_digest=str(new_manifest["manifest_digest"]),
                actor=approval.approved_by,
                candidate_id=candidate_id,
                skill_name=skill_name,
                approved_by=approval.approved_by,
                artifact_digest=artifact.revision_digest,
            ).to_dict(),
        )
        return SkillInstallReceipt(
            assistant_id=assistant_id,
            candidate_id=candidate_id,
            skill_name=skill_name,
            skill_path=str(skill_dir),
            state=artifact.state.value,
            approved_by=approval.approved_by,
            promoted_at=promoted_at,
        )

    # ── 0067 三闸 ────────────────────────────────────────────────────

    def _gate_identity(self, card: Mapping[str, Any], assistant_id: str) -> None:
        """identity 闸：候选必须属于本助理，审批凭据必须合法。"""
        if str(card.get("assistant_id", "")) != assistant_id:
            raise PromoteGateRejected(
                f"identity 闸拒绝:候选 assistant={card.get('assistant_id')!r} "
                f"不属于 {assistant_id!r}"
            )

    def _gate_invariant(self, card: Mapping[str, Any], home: Path, draft_md: str) -> None:
        """invariant 闸：候选结构完整 + 目标 skill 位未被占用 + 状态迁移合法。

        Home 配置面 digest 一致性由 ``catalog.get`` 在 promote 入口已守门
        （I-A3 fail-closed），本闸不重算。
        """
        for field_name in ("candidate_id", "skill_name", "task_ref"):
            if not str(card.get(field_name, "")).strip():
                raise PromoteGateRejected(f"invariant 闸拒绝:提案卡缺 {field_name!r}")
        skill_dir = home / "skills" / str(card["skill_name"])
        if skill_dir.exists():
            raise PromoteGateRejected(f"invariant 闸拒绝:skill 目录已存在 {skill_dir}")
        if not draft_md.strip():
            raise PromoteGateRejected("invariant 闸拒绝:草稿正文为空")
        if not is_legal_transition(ArtifactState.DRAFT, ArtifactState.VERIFIED):
            raise PromoteGateRejected("invariant 闸拒绝:0067 状态机不允许 DRAFT→VERIFIED")

    def _gate_experiment(self, card: Mapping[str, Any]) -> None:
        """experiment 闸：只有 experiment 候选可提升；非 experiment 拒收。"""
        status = str(card.get("status", ""))
        if status != _EXPERIMENT_SCOPE:
            raise PromoteGateRejected(f"experiment 闸拒绝:候选状态={status!r},仅 experiment 可提升")

    # ── 内部 ─────────────────────────────────────────────────────────

    def _write_pending_card(
        self,
        home: Path,
        *,
        assistant_id: str,
        revision_seq: int,
        manifest_digest: str,
        candidate: SkillAcquisitionCandidate,
    ) -> str:
        """写提案卡（元数据）+ 草稿正文；返回草稿 digest。不触碰 ``skills/``。"""
        pending_dir = home / _PENDING_DIR
        pending_dir.mkdir(parents=True, exist_ok=True)
        draft_path = pending_dir / f"{candidate.candidate_id}.md"
        draft_path.write_text(candidate.procedure, encoding="utf-8")
        draft_digest = f"sha256:{hashlib.sha256(candidate.procedure.encode('utf-8')).hexdigest()}"
        card: dict[str, Any] = {
            "candidate_id": candidate.candidate_id,
            "assistant_id": assistant_id,
            "skill_name": _skill_name(candidate.candidate_id),
            "task_ref": candidate.task_ref,
            "confidence": candidate.confidence,
            "evidence_refs": list(candidate.evidence_refs),
            "status": candidate.status,
            "scope": _EXPERIMENT_SCOPE,
            "created_at": _iso(self._clock()),
            "revision_seq": revision_seq,
            "manifest_digest": manifest_digest,
            "draft_digest": draft_digest,
        }
        (pending_dir / f"{candidate.candidate_id}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return draft_digest

    def _emit(self, event: str, payload: Mapping[str, Any]) -> None:
        """发 EP；无 emitter 时仅 log（单元测试路径）。"""
        if self._emit_fn is None:
            log.info("assistant.evolve.ep.no_emitter", ep=event, payload=dict(payload))
            return
        self._emit_fn(event, dict(payload))


# ── helpers ──────────────────────────────────────────────────────────


def _content_digest(text: str) -> str:
    """``sha256:<hex>`` 内容 digest（与 _home_layout.sha256_digest 同形态）。"""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _iso(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _skill_name(candidate_id: str) -> str:
    """candidate_id → skill 目录名（``evolved-<digest8>``）。"""
    suffix = candidate_id.rsplit("-", 1)[-1]
    return f"evolved-{suffix[:8]}"


def _draft_procedure(*, assistant_id: str, task_ref: str, digest: ObservationDigest) -> str:
    """PR-8 启发式草稿正文（模板蒸馏；离线 GEPA = ADR-0187.2 不做）。

    本正文只落 ``{home}/.evolve/pending/`` 与提升后的 ``skills/``，
    禁止进 EP payload / spine（ADR-0187 §3 D2 末段）。
    """
    run_list = "\n".join(f"- {run_id}" for run_id in digest.run_ids)
    return (
        f"# evolved skill for {assistant_id}\n"
        f"\n"
        f"task_ref: {task_ref}\n"
        f"observed_at: {digest.observed_at}\n"
        f"\n"
        f"## Observed runs\n"
        f"{run_list}\n"
        f"\n"
        f"## Procedure\n"
        f"1. Replay the observed procedure for `{task_ref}`.\n"
        f"2. Keep effects within the assistant workspace grant.\n"
    )


def _read_card(card_path: Path) -> dict[str, Any]:
    """读提案卡；非 dict / 缺 candidate_id 抛 :cls:`UnknownCandidate`。"""
    try:
        data = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UnknownCandidate(f"提案卡不可读: {card_path} ({exc})") from exc
    if not isinstance(data, dict) or not str(data.get("candidate_id", "")).strip():
        raise UnknownCandidate(f"提案卡结构非法: {card_path}")
    return data


# ── Plugin manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.evolve",
    provides=(ASSISTANT_EVOLVE.key,),
    requires=(ASSISTANT_CATALOG.key, "event.bus"),
    implements=[AssistantEvolve, SkillAcquirer],
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.FILESYSTEM,),
    description=(
        "助理域 SkillAcquirer：run 轨迹蒸馏 experiment 候选,审批 + 0067 三闸后"
        "写 {home}/skills/;默认不落盘,不做离线 GEPA(ADR-0187.2)。"
    ),
    test_suite="tests/plugins/assistant/test_evolve.py",
    functional_group=FunctionalGroup.G11_CREATION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G11_CREATION,
            control_slots=(ControlSlot.OBSERVE_CHECKPOINT,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(
            grants=("assistant.evolve.propose", "assistant.evolve.promote")
        ),
        observability=EvidenceContract(
            descriptors=(
                ASSISTANT_SKILL_EVOLVED_PROPOSED,
                ASSISTANT_SKILL_EVOLVED_PROMOTED,
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key,),
        emits=(
            ASSISTANT_SKILL_EVOLVED_PROPOSED,
            ASSISTANT_SKILL_EVOLVED_PROMOTED,
        ),
        state_mutation="reducer-only",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """assistant.evolve plugin boot：取 catalog + 暴露 ``assistant.evolve``。

    根路径经 ``catalog.get(...).home_path`` 间接取得；本插件不读
    ``os.environ``、不持有 assistants_root（ADR-0187 §6 删除条件）。
    """
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"assistant.evolve requires {ASSISTANT_CATALOG.key} 为 AssistantCatalog,"
            f"得到 {type(catalog).__name__}"
        )

    def _emit(event: str, payload: Mapping[str, Any]) -> Any:
        return ctx.emit(event, dict(payload))

    impl = _AssistantEvolveImpl(
        catalog=catalog,
        event_emitter=_emit,
        min_confidence=config.min_confidence,
        min_evidence=config.min_evidence,
        draft_confidence=config.draft_confidence,
    )
    ctx.provide(ASSISTANT_EVOLVE.key, impl)


# 用于测试在不接 ctx 时直接构造
AssistantEvolveImpl = _AssistantEvolveImpl

__all__ = [
    "AssistantEvolveError",
    "AssistantEvolveImpl",
    "Config",
    "MissingWriteApproval",
    "PromoteGateRejected",
    "UnknownCandidate",
    "setup",
]
