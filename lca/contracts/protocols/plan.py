"""CompiledRunPlan 不可变契约（ADR-0068 §一 + ADR-0074 PR-3）。

CompiledRunPlan = CapabilityPlan + ControlPlan + ScopePlan。运行时
唯一可读输入；不可在运行时修改。任何 plan_ref 引用必须能重放出
CapabilityPlan + ControlPlan + ScopePlan 三子 plan（PR-6 落地）。

字段：

- ``capability`` — CapabilityPlan（PR-2.5）
- ``control`` — ControlPlan（PR-1）
- ``scope`` — ScopePlan（PR-3 最小版）
- ``profile_path`` — 来源 profile 路径
- ``plan_ref`` — canonical hash（cross-process / cross-run 稳定）
- ``plan_version`` — CompiledRunPlan schema 版本
- ``input_provenance`` — 输入 provenance（profile / bundle / patch / task）
- ``revision`` — 用户声明的 plan 版本字符串

**plan_ref 派生算法**：

1. capability_plan_hash() → 16 字符
2. control_plan_hash() → 16 字符
3. scope_plan_hash() → 16 字符
4. SHA-256(cap_hash + control_hash + scope_hash + profile_path +
   plan_version + sorted(input_provenance items)) → 16 字符

跨进程 / 跨运行稳定（PR-3 plan_hash determinism property test 守护）。

ADR-0015 contracts 纯类型契约：``CompiledRunPlan`` 不放方法，
访问器 module-level 函数（``compiled_run_plan_ref`` /
``compiled_run_plan_to_dict``）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from lca.contracts.protocols.capability_plan import (
    CapabilityPlan,
    capability_plan_hash,
)
from lca.contracts.protocols.control_plan import (
    ControlPlan,
    compute_control_plan_hash,
)
from lca.contracts.protocols.scope_plan import (
    ScopePlan,
    scope_plan_hash,
)

# Schema version for CompiledRunPlan (bump on breaking format change)
COMPILED_RUN_PLAN_VERSION: str = "v1"


@dataclass(frozen=True, slots=True)
class CompiledRunPlan:
    """CompiledRunPlan 不可变契约（ADR-0068 §一 + ADR-0074 PR-3）。

    运行时唯一可读输入。任何修改必须重新编译（→ 新 plan_ref），
    而非在运行时 mutate。
    """

    profile_path: str
    capability: CapabilityPlan
    control: ControlPlan
    scope: ScopePlan
    plan_version: str = COMPILED_RUN_PLAN_VERSION
    input_provenance: tuple[tuple[str, str], ...] = ()
    revision: str = "v1"

    def __post_init__(self) -> None:
        if not self.profile_path:
            raise ValueError("CompiledRunPlan.profile_path must be non-empty")
        if not isinstance(self.input_provenance, tuple):
            object.__setattr__(self, "input_provenance", tuple(self.input_provenance))
        # input_provenance: each (kind, path) is normalized to tuple of str
        normalized: list[tuple[str, str]] = []
        for item in self.input_provenance:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError(f"input_provenance item must be (kind, path) tuple, got {item!r}")
            kind, path = item
            normalized.append((str(kind), str(path)))
        object.__setattr__(self, "input_provenance", tuple(normalized))


# ── Module-level accessors / factories (ADR-0015) ───────────────────


def compiled_run_plan_ref(plan: CompiledRunPlan) -> str:
    """CompiledRunPlan plan_ref = 16 字符 SHA-256。

    输入：

    - 3 个子 plan 的 hash（capability / control / scope）
    - profile_path
    - plan_version
    - sorted(input_provenance) (kind, path) pairs

    同输入 → 同 plan_ref（PR-3 plan_hash determinism property test）。
    """
    cap_hash = capability_plan_hash(plan.capability)
    control_hash = compute_control_plan_hash(plan.control.entries, plan.control.profile_path)
    scope_hash = scope_plan_hash(plan.scope)
    payload = {
        "capability": cap_hash,
        "control": control_hash,
        "scope": scope_hash,
        "profile_path": plan.profile_path,
        "plan_version": plan.plan_version,
        "input_provenance": sorted((kind, path) for kind, path in plan.input_provenance),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def capability_sub_plan_hash(plan: CompiledRunPlan) -> str:
    """CompiledRunPlan.capability 子 plan 的 hash。"""
    return capability_plan_hash(plan.capability)


def control_sub_plan_hash(plan: CompiledRunPlan) -> str:
    """CompiledRunPlan.control 子 plan 的 hash。"""
    return compute_control_plan_hash(plan.control.entries, plan.control.profile_path)


def scope_sub_plan_hash(plan: CompiledRunPlan) -> str:
    """CompiledRunPlan.scope 子 plan 的 hash。"""
    return scope_plan_hash(plan.scope)


def plan_ref_of(plan: CompiledRunPlan) -> str:
    """``compiled_run_plan_ref`` 别名（可读性）。"""
    return compiled_run_plan_ref(plan)


def compiled_run_plan_to_dict(plan: CompiledRunPlan) -> dict[str, Any]:
    """JSON 友好字典（plan_ref + 3 子 plan 摘要）。"""
    return {
        "profile_path": plan.profile_path,
        "plan_version": plan.plan_version,
        "plan_ref": compiled_run_plan_ref(plan),
        "revision": plan.revision,
        "input_provenance": [{"kind": kind, "path": path} for kind, path in plan.input_provenance],
        "capability": {
            "profile_path": plan.capability.profile_path,
            "revision": plan.capability.revision,
            "plan_hash": capability_plan_hash(plan.capability),
            "binding_count": len(plan.capability.provider_bindings),
            "relation_count": len(plan.capability.relations),
        },
        "control": {
            "profile_path": plan.control.profile_path,
            "plan_hash": compute_control_plan_hash(plan.control.entries, plan.control.profile_path),
            "entry_count": len(plan.control.entries),
            "covered_slots": sorted(s.value for s in plan.control.by_slot),
        },
        "scope": {
            "profile_path": plan.scope.profile_path,
            "lifecycle": plan.scope.lifecycle.value,
            "visibility": [s.value for s in plan.scope.visibility],
            "acl_grants": list(plan.scope.acl_grants),
            "budget_ceiling": {
                "max_tokens": plan.scope.budget_ceiling.max_tokens,
                "max_wall_clock_seconds": plan.scope.budget_ceiling.max_wall_clock_seconds,
                "max_tool_calls": plan.scope.budget_ceiling.max_tool_calls,
                "max_steps": plan.scope.budget_ceiling.max_steps,
                "max_cost_cents": plan.scope.budget_ceiling.max_cost_cents,
            },
            "plan_hash": scope_plan_hash(plan.scope),
        },
    }


def build_input_provenance(
    profile_path: str,
    bundles: Iterable[str],
    patches: Iterable[str] = (),
    task_id: str | None = None,
    env_fingerprint: str | None = None,
) -> tuple[tuple[str, str], ...]:
    """从 profile / bundles / patches / task 构造 input_provenance。

    provenance 项是 ``(kind, path)`` tuple，``kind`` ∈ ``profile`` /
    ``bundle`` / ``patch`` / ``task`` / ``env``，保留输入声明顺序以便解释
    profile 的装配来源。``compiled_run_plan_ref`` 会在哈希时排序该数据。
    """
    out: list[tuple[str, str]] = []
    out.append(("profile", str(profile_path)))
    for b in bundles:
        out.append(("bundle", str(b)))
    for p in patches:
        out.append(("patch", str(p)))
    if task_id is not None:
        out.append(("task", str(task_id)))
    if env_fingerprint is not None:
        out.append(("env", str(env_fingerprint)))
    return tuple(out)


__all__ = [
    "COMPILED_RUN_PLAN_VERSION",
    "CompiledRunPlan",
    "build_input_provenance",
    "capability_sub_plan_hash",
    "compiled_run_plan_ref",
    "compiled_run_plan_to_dict",
    "control_sub_plan_hash",
    "plan_ref_of",
    "scope_sub_plan_hash",
]
