"""Creator four-face vocabulary and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from lca.contracts.atoms.artifact_state import ArtifactState


class CreatorFace(str, Enum):
    """Creator 4 faces (ADR-0074 §三 V7 acceptance)。

    字符串值稳定（CLI / journal / plan_ref 引用）；新增 face 必须经
    ADR 批准。
    """

    INSPECT = "inspect"
    AUTHOR = "author"
    VALIDATE = "validate"
    PROMOTE = "promote"


@dataclass(frozen=True, slots=True)
class PromoteSpec:
    """promote action 参数规格（V7 acceptance §5.2）。

    Attributes:
        target_scope: 目标 scope（release / profile / agent / run / turn /
            experiment / device）。``None`` = 默认 = run.
        rollback: True → ACTIVE 到 RETIRED；False = VERIFIED 到 ACTIVE。
        preset_id: release promote 的 preset 目录名。
    """

    target_scope: str | None = None
    rollback: bool = False
    preset_id: str | None = None


@dataclass(frozen=True, slots=True)
class CreatorResult:
    """Creator face 输出（统一返回类型）。

    Attributes:
        face: 实际执行的 face
        state_after: 执行后面向的状态（PR-8 ArtifactState）
        payload: face-specific data dict (inspect graph / author result /
            validate verdict / promote migration result)
        plan_ref: 关联 plan_ref（V5 守护；PR-9 stage 2 接入）
        metadata: 插件可扩展字段
    """

    face: CreatorFace
    state_after: ArtifactState
    payload: dict[str, Any] = field(default_factory=dict)
    plan_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Module-level face operations (ADR-0015) ─────────────────────────


def parse_creator_face(value: object) -> CreatorFace:
    """字符串 / 枚举 → CreatorFace。"""
    if isinstance(value, CreatorFace):
        return value
    if isinstance(value, str):
        try:
            return CreatorFace(value)
        except ValueError as exc:
            raise ValueError(
                f"unknown creator face {value!r}; valid: {[f.value for f in CreatorFace]}"
            ) from exc
    raise TypeError(f"creator face must be str or CreatorFace, got {type(value).__name__}")


def all_creator_faces() -> tuple[CreatorFace, ...]:
    """全部 Creator faces（enum 顺序）。"""
    return tuple(CreatorFace)


__all__ = [
    "CreatorFace",
    "CreatorResult",
    "PromoteSpec",
    "all_creator_faces",
    "parse_creator_face",
]
