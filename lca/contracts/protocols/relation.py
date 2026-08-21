"""TypedRelation 数据契约（ADR-0069 §三 + ADR-0074 PR-2.5）。

TypedRelation 是 CapabilityPlan / Profile 间关系的 typed 表达。
dataclass 命名为 ``TypedRelation``（区别于 ``Relation`` enum，
后者在 ``lca.contracts.atoms.relation`` 中定义关系代数闭集）。

字段：

- ``source`` — 关系发起方 plugin id
- ``target`` — 关系接收方 plugin id 或 capability key
- ``kind`` — 11 种关系代数之一（Relation enum）
- ``evidence`` — Journal catalog EventDescriptor 名字（可空）
- ``scope`` — 关系有效 scope（release / profile / agent / run / turn /
  invocation / experiment / device）
- ``weight`` — 关系强度（默认 1.0；用于图谱可视化的边粗细）

PR-2.5 阶段：CapabilityPlan.relations 接受 ``list[TypedRelation]``，
Resolve 期验证：relation.kind ∈ 11 闭集；source / target 引用必须
指向真实 plugin / capability（缺失 → ProfileResolveError）。

ADR-0015 contracts 纯类型契约：``TypedRelation`` 不放方法，访问器
module-level 函数（``typed_relation_to_dict`` /
``typed_relations_from_iter``）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.relation import Relation, parse_relation
from lca.contracts.atoms.scope import Scope, canonical_scope, parse_scope


@dataclass(frozen=True, slots=True)
class TypedRelation:
    """单条 typed 关系（ADR-0069 §三）。

    ``kind`` 是 ``Relation`` enum（11 项闭集）；``source`` / ``target``
    是 plugin id 或 capability key。``scope`` 通过 ``canonical_scope``
    折叠（invocation → turn）；``weight`` 默认 1.0，可用于图谱粗细。
    """

    source: str
    target: str
    kind: Relation
    evidence: tuple[str, ...] = ()
    scope: Scope | None = None
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source:
            raise ValueError(f"TypedRelation.source must be non-empty str, got {self.source!r}")
        if not isinstance(self.target, str) or not self.target:
            raise ValueError(f"TypedRelation.target must be non-empty str, got {self.target!r}")
        if not isinstance(self.kind, Relation):
            object.__setattr__(self, "kind", parse_relation(self.kind))
        if not isinstance(self.evidence, tuple):
            object.__setattr__(self, "evidence", tuple(self.evidence))
        if self.scope is not None and not isinstance(self.scope, Scope):
            object.__setattr__(self, "scope", parse_scope(self.scope))
        if not isinstance(self.weight, (int, float)):
            raise ValueError(
                f"TypedRelation.weight must be number, got {type(self.weight).__name__}"
            )
        if self.weight < 0:
            raise ValueError(f"TypedRelation.weight must be >= 0, got {self.weight}")


# ── Module-level accessors / factories (ADR-0015) ───────────────────


def typed_relation_to_dict(relation: TypedRelation) -> dict[str, Any]:
    """JSON 友好字典。"""
    canonical = canonical_scope(relation.scope) if relation.scope is not None else None
    return {
        "source": relation.source,
        "target": relation.target,
        "kind": relation.kind.value,
        "evidence": list(relation.evidence),
        "scope": relation.scope.value if relation.scope is not None else None,
        "scope_canonical": canonical.value if canonical is not None else None,
        "weight": relation.weight,
    }


def typed_relations_from_iter(values: Iterable[Any]) -> tuple[TypedRelation, ...]:
    """从 raw 列表构造 ``tuple[TypedRelation, ...]``，每条 raw 校验。

    接受 dict / TypedRelation 两种输入：

    - dict 必须含 ``source`` / ``target`` / ``kind``；其他字段可选
    - TypedRelation 实例直接保留

    任何 dict 缺字段或字段非法 → ``ValueError``。
    """
    out: list[TypedRelation] = []
    for idx, raw in enumerate(values):
        if isinstance(raw, TypedRelation):
            out.append(raw)
            continue
        if not isinstance(raw, dict):
            raise ValueError(
                f"typed_relation[{idx}] must be dict or TypedRelation, got {type(raw).__name__}"
            )
        if "source" not in raw or "target" not in raw or "kind" not in raw:
            raise ValueError(
                f"typed_relation[{idx}] missing required field (need source/target/kind)"
            )
        out.append(
            TypedRelation(
                source=str(raw["source"]),
                target=str(raw["target"]),
                kind=parse_relation(raw["kind"]),
                evidence=tuple(str(e) for e in raw.get("evidence", ()) or ()),
                scope=parse_scope(raw["scope"]) if raw.get("scope") else None,
                weight=float(raw.get("weight", 1.0)),
            )
        )
    return tuple(out)


__all__ = [
    "TypedRelation",
    "typed_relation_to_dict",
    "typed_relations_from_iter",
]
