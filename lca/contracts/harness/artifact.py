"""CapabilityArtifact + ArtifactController（ADR-0068 §一 + ADR-0074 PR-8）。

PR-8 阶段：4 状态机（``DRAFT`` / ``VERIFIED`` / ``ACTIVE`` / ``RETIRED``）+ state migration API。

字段（CapabilityArtifact frozen dataclass）：

- ``logical_id`` —— 唯一逻辑标识（跨多次部署稳定）
- ``revision_digest`` —— 内容 hash（capability content fingerprint）
- ``state`` —— ArtifactState enum
- ``scope`` —— 当前可见 scope（release / profile / agent / run / turn /
  invocation / experiment / device；ADR-0074 §三压缩 8 → 7）
- ``grants`` —— capability grant ceiling（V8 单调；子 ⊆ 父）
- ``legacy_state`` —— 旧 8 状态码（PR-8 stage migration 用；新 artifact 为 None）
- ``metadata`` —— 插件可扩展字段

ArtifactController 提供：

- ``migrate(artifact, target_state)`` —— 校验 + 执行状态迁移；非法迁移抛
  ``InvalidStateTransition``
- ``legal_next_states(artifact)`` —— 当前状态可迁移到哪些目标
- ``migrate_to_retired(artifact)`` —— 便利方法：ACTIVE → RETIRED
- ``migrate_to_active(artifact)`` —— 便利方法：VERIFIED → ACTIVE
- ``migrate_to_verified(artifact)`` —— 便利方法：DRAFT → VERIFIED

PR-8 stage 2 接入 8→4 状态迁移映射（tracker §18.1）：
- PARSED → DRAFT
- DECLARED → DRAFT
- STAGED → ACTIVE
- QUIESCING → ACTIVE（quiescing 是 ACTIVE 退出协议）
- ROLLED_BACK → RETIRED

ADR-0015 contracts 纯类型契约：CapabilityArtifact / ArtifactState 不放方法，
所有派生 / 状态迁移通过 module-level functions（``migrate_artifact`` 等）。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.atoms.artifact_state import (
    LEGAL_TRANSITIONS,
    ArtifactState,
    is_legal_transition,
)
from lca.contracts.atoms.scope import Scope, parse_scope


class InvalidStateTransitionError(ValueError):
    """非法状态迁移（V6 acceptance §5.1）。

    Raised when ArtifactController.migrate() rejects a state transition
    that is not in LEGAL_TRANSITIONS.
    """


@dataclass(frozen=True, slots=True)
class CapabilityArtifact:
    """Artifact 不可变契约（PR-8 + ADR-0068 §一）。

    字段：

    - ``logical_id`` —— 唯一逻辑标识（跨多次部署稳定）
    - ``revision_digest`` —— 内容 hash（capability content fingerprint）
    - ``state`` —— ArtifactState enum
    - ``scope`` —— 当前可见 scope（V8 单调：子 ⊆ 父）
    - ``grants`` —— capability grant ceiling（V8 单调）
    - ``legacy_state`` —— 旧 8 状态码（migration 用；None = 新 artifact）
    - ``metadata`` —— 插件可扩展字段

    PR-8 阶段：ArtifactController 是 fabric 数据层（不动 ``mount`` /
    ``unmount`` runtime 接线，留 PR-10 golden profile 阶段）。
    """

    logical_id: str
    revision_digest: str
    state: ArtifactState
    scope: Scope
    grants: tuple[str, ...] = ()
    legacy_state: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.logical_id, str) or not self.logical_id:
            raise ValueError(
                f"CapabilityArtifact.logical_id must be non-empty str, got {self.logical_id!r}"
            )
        if not isinstance(self.revision_digest, str) or not self.revision_digest:
            raise ValueError(
                f"CapabilityArtifact.revision_digest must be non-empty str, "
                f"got {self.revision_digest!r}"
            )
        if not isinstance(self.state, ArtifactState):
            object.__setattr__(self, "state", ArtifactState(self.state))
        if not isinstance(self.scope, Scope):
            object.__setattr__(self, "scope", parse_scope(self.scope))
        if not isinstance(self.grants, tuple):
            object.__setattr__(self, "grants", tuple(self.grants))


# ── Module-level accessors / factories (ADR-0015) ───────────────────


def artifact_with_state(artifact: CapabilityArtifact, state: ArtifactState) -> CapabilityArtifact:
    """返回 new CapabilityArtifact with updated state (frozen dataclass immutability)。"""
    return CapabilityArtifact(
        logical_id=artifact.logical_id,
        revision_digest=artifact.revision_digest,
        state=state,
        scope=artifact.scope,
        grants=artifact.grants,
        legacy_state=artifact.legacy_state,
        metadata=artifact.metadata,
        version=artifact.version,
    )


def legal_next_states(artifact: CapabilityArtifact) -> tuple[ArtifactState, ...]:
    """当前状态下合法的迁移目标（去重 + enum 顺序）。"""
    seen: set[ArtifactState] = set()
    out: list[ArtifactState] = []
    for src, tgt in sorted(
        LEGAL_TRANSITIONS,
        key=lambda p: (list(ArtifactState).index(p[1]), p[0].value),
    ):
        if src == artifact.state and tgt not in seen:
            out.append(tgt)
            seen.add(tgt)
    return tuple(out)


def migrate_artifact(
    artifact: CapabilityArtifact,
    target_state: ArtifactState,
) -> CapabilityArtifact:
    """状态迁移主入口（V6 acceptance）。

    Raises:
        InvalidStateTransition: 非法迁移（如 RETIRED → DRAFT）
    """
    if not is_legal_transition(artifact.state, target_state):
        legal = legal_next_states(artifact)
        raise InvalidStateTransitionError(
            f"CapabilityArtifact.logical_id={artifact.logical_id!r}: "
            f"illegal state transition {artifact.state.value!r} → {target_state.value!r}. "
            f"Legal next states from {artifact.state.value!r}: "
            f"{[s.value for s in legal] or '(terminal — no legal transitions)'}"
        )
    return artifact_with_state(artifact, target_state)


def migrate_to_verified(
    artifact: CapabilityArtifact,
) -> CapabilityArtifact:
    """便利方法：DRAFT → VERIFIED。"""
    return migrate_artifact(artifact, ArtifactState.VERIFIED)


def migrate_to_active(
    artifact: CapabilityArtifact,
) -> CapabilityArtifact:
    """便利方法：VERIFIED → ACTIVE。"""
    return migrate_artifact(artifact, ArtifactState.ACTIVE)


def migrate_to_retired(
    artifact: CapabilityArtifact,
) -> CapabilityArtifact:
    """便利方法：ACTIVE → RETIRED。"""
    return migrate_artifact(artifact, ArtifactState.RETIRED)


def is_terminal_state(artifact: CapabilityArtifact) -> bool:
    """artifact 是否在终态（RETIRED 不可逆）。"""
    return artifact.state is ArtifactState.RETIRED


# ── 8 → 4 状态迁移映射（tracker §18.1 + ADR-0074 §三）──────────────


LEGACY_TO_NEW_STATE: dict[str, ArtifactState] = {
    "draft": ArtifactState.DRAFT,
    "parsed": ArtifactState.DRAFT,  # PARSED → DRAFT (VERIFIED 的子步骤)
    "declared": ArtifactState.DRAFT,  # DECLARED → DRAFT (VERIFIED 的子步骤)
    "verified": ArtifactState.VERIFIED,
    "staged": ArtifactState.ACTIVE,  # STAGED → ACTIVE (deploy mode 非独立状态)
    "active": ArtifactState.ACTIVE,
    "quiescing": ArtifactState.ACTIVE,  # QUIESCING → ACTIVE (退出协议)
    "retired": ArtifactState.RETIRED,
    "rolled_back": ArtifactState.RETIRED,  # ROLLED_BACK → RETIRED (子分支)
}


def migrate_legacy_state(
    artifact: CapabilityArtifact,
) -> CapabilityArtifact:
    """8 状态码 → 4 状态机迁移（PR-8 stage 2 / PR-10 golden profile）。"""
    if artifact.legacy_state is None:
        return artifact  # 已迁移；no-op
    if artifact.state is not ArtifactState.DRAFT:
        raise ValueError(
            f"migrate_legacy_state: artifact {artifact.logical_id!r} "
            f"already in {artifact.state.value!r}; cannot migrate legacy_state"
        )
    new_state = LEGACY_TO_NEW_STATE.get(artifact.legacy_state)
    if new_state is None:
        raise ValueError(
            f"unknown legacy state {artifact.legacy_state!r}; "
            f"valid: {sorted(LEGACY_TO_NEW_STATE.keys())}"
        )
    return CapabilityArtifact(
        logical_id=artifact.logical_id,
        revision_digest=artifact.revision_digest,
        state=new_state,
        scope=artifact.scope,
        grants=artifact.grants,
        legacy_state=None,  # clear legacy marker
        metadata=artifact.metadata,
        version=artifact.version,
    )


def make_capability_artifact(
    logical_id: str,
    content: bytes | str,
    scope: Scope | str = Scope.RUN,
    state: ArtifactState | str = ArtifactState.DRAFT,
    grants: Iterable[str] = (),
    legacy_state: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CapabilityArtifact:
    """工厂方法：自动计算 revision_digest (SHA-256 hex 16 char)。

    Args:
        logical_id: 唯一逻辑标识
        content: artifact content (str or bytes)；用于 revision_digest 计算
        scope: 当前可见 scope（默认 RUN）
        state: 初始状态（默认 DRAFT）
        grants: capability grant ceiling
        legacy_state: 旧 8 状态码（migration 用；新 artifact 为 None）
        metadata: 插件可扩展字段
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()[:16]
    if isinstance(scope, str):
        scope = parse_scope(scope)
    if isinstance(state, str):
        state = ArtifactState(state)
    return CapabilityArtifact(
        logical_id=logical_id,
        revision_digest=digest,
        state=state,
        scope=scope,
        grants=tuple(grants),
        legacy_state=legacy_state,
        metadata=dict(metadata) if metadata else {},
    )


def capability_artifact_to_dict(artifact: CapabilityArtifact) -> dict[str, Any]:
    """JSON 友好字典。"""
    return {
        "logical_id": artifact.logical_id,
        "revision_digest": artifact.revision_digest,
        "state": artifact.state.value,
        "scope": artifact.scope.value,
        "grants": list(artifact.grants),
        "legacy_state": artifact.legacy_state,
        "metadata": dict(artifact.metadata),
        "version": artifact.version,
    }


# ── ArtifactController facade（PR-8 stage 2 留 PR-10 接入）─────


@dataclass(frozen=True, slots=True)
class ArtifactController:
    """Artifact state machine controller（PR-8 数据面 + stage 2 facade）。

    PR-8 阶段：thin dataclass；所有派生方法走 module-level functions。
    runtime 集成（cordis_control.mount / unmount 调用 ArtifactController）
    留 PR-10 golden profile 阶段（acceptance §7.3）。

    注意（ADR-0015 contracts 纯类型契约）：ArtifactController 不放方法；
    派生操作通过 module-level functions（``controller_migrate`` /
    ``controller_legal_next_states`` / ``controller_migrate_legacy``）。
    """

    name: str = "default"
    """controller name（multi-controller 场景留扩展点；PR-8 阶段 single）。"""


# ── Module-level controller accessors (ADR-0015) ────────────────


def controller_migrate(
    controller: ArtifactController,
    artifact: CapabilityArtifact,
    target_state: ArtifactState,
) -> CapabilityArtifact:
    """``controller.migrate(artifact, target)`` 等价 module-level helper。"""
    return migrate_artifact(artifact, target_state)


def controller_legal_next_states(
    controller: ArtifactController,
    artifact: CapabilityArtifact,
) -> tuple[ArtifactState, ...]:
    """``controller.legal_next_states(artifact)`` 等价 module-level helper。"""
    return legal_next_states(artifact)


def controller_migrate_legacy(
    controller: ArtifactController,
    artifact: CapabilityArtifact,
) -> CapabilityArtifact:
    """``controller.migrate_legacy(artifact)`` 等价 module-level helper。"""
    return migrate_legacy_state(artifact)


__all__ = [
    "LEGACY_TO_NEW_STATE",
    "ArtifactController",
    "CapabilityArtifact",
    "InvalidStateTransitionError",
    "artifact_with_state",
    "capability_artifact_to_dict",
    "controller_legal_next_states",
    "controller_migrate",
    "controller_migrate_legacy",
    "is_terminal_state",
    "legal_next_states",
    "make_capability_artifact",
    "migrate_artifact",
    "migrate_legacy_state",
    "migrate_to_active",
    "migrate_to_retired",
    "migrate_to_verified",
]
