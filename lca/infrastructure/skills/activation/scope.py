"""Run-scoped activated operational skills (for run_skill_script).

PR-E 收口(2026-09-08): ``register_activated`` 不再只动 ContextVar —— 同步
转发到 :class:`SkillActivationReducerBridge`,把激活 fold 进 reducer 单一
写路径(ADR-0186 / C4 / AGENTS.md §2.2)。prompt assembler 读
``state.activated_skills`` 时看到完整激活列表,不再让 LLM 重复
``activate_skill``(回归 run_2910e20390f9 的 step 2/3/4 重复激活)。
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token

from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.protocols.memory.operational_skills import SkillNotFoundError
from lca.infrastructure.skills.activation.bridge import bridge

# Re-export for backward compatibility
__all__ = [
    "MAX_ACTIVATED_SKILLS_PER_RUN",
    "ActivatedSkill",
    "activated_skills_scope",
    "can_activate",
    "get_activated_skills",
    "get_newly_activated",
    "register_activated",
    "resolve_skill_for_exec",
    "unregister_activated",
]

_activated_skills: ContextVar[tuple[ActivatedSkill, ...]] = ContextVar(
    "lca_activated_skills",
    default=(),
)


MAX_ACTIVATED_SKILLS_PER_RUN = 8
"""Per-run cap on concurrently activated skills.

Rationale: each activation injects a full SKILL.md (typically 2-8 KB) into the
run's context, and the activated list is rendered into every prompt assembly.
8 bounds the injected context to a manageable size while covering realistic
multi-skill tasks; beyond that the model must explicitly deactivate one first
instead of silently accumulating state the run can never shed.
"""


def get_activated_skills() -> tuple[ActivatedSkill, ...]:
    return _activated_skills.get()


def register_activated(skill_id: str, name: str) -> None:
    current = _activated_skills.get()
    entry = ActivatedSkill(skill_id=skill_id, name=name)
    filtered = tuple(item for item in current if item.skill_id != skill_id)
    _activated_skills.set((*filtered, entry))
    # PR-E:同步转发到 reducer(若 run 已 install bridge)。bridge 未 install
    # 时是 no-op,允许 import-time / 测试 fixture 早期调用不报错。
    bridge.handle(skill_id=skill_id, name=name)


def can_activate(skill_id: str) -> bool:
    """Whether activating ``skill_id`` fits the per-run budget.

    Re-activating an already-activated skill is always allowed (idempotent and
    does not grow the context).
    """
    sid = skill_id.strip()
    current = _activated_skills.get()
    if any(item.skill_id == sid or item.name == sid for item in current):
        return True
    return len(current) < MAX_ACTIVATED_SKILLS_PER_RUN


def unregister_activated(skill_id: str) -> bool:
    """Remove a skill from the run-scoped activation set. Idempotent.

    Returns True when an entry was actually removed. Forwards to the reducer
    bridge so ``state.activated_skills`` stays in sync (no-op when the bridge
    is not installed, e.g. import-time or unit tests).
    """
    sid = skill_id.strip()
    current = _activated_skills.get()
    target = next(
        (item for item in current if item.skill_id == sid or item.name == sid),
        None,
    )
    if target is None:
        return False
    _activated_skills.set(
        tuple(item for item in current if item.skill_id != target.skill_id)
    )
    bridge.handle_deactivation(skill_id=target.skill_id)
    return True


def get_newly_activated(
    known: Sequence[ActivatedSkill],
) -> list[ActivatedSkill]:
    """Return skills in contextvar that are not yet in *known* (by skill_id)."""
    known_ids = {s.skill_id for s in known}
    return [s for s in _activated_skills.get() if s.skill_id not in known_ids]


def resolve_skill_for_exec(skill_id: str | None) -> ActivatedSkill:
    activated = get_activated_skills()
    if skill_id:
        sid = skill_id.strip()
        for item in reversed(activated):
            if item.skill_id == sid or item.name == sid:
                return item
        raise SkillNotFoundError(f"未激活 skill: {skill_id!r}；请先 activate_skill")
    if not activated:
        raise SkillNotFoundError("无已激活 skill；请先 activate_skill")
    return activated[-1]


@contextmanager
def activated_skills_scope(items: Sequence[ActivatedSkill]) -> Iterator[tuple[ActivatedSkill, ...]]:
    cleaned = tuple(items)
    token: Token[tuple[ActivatedSkill, ...]] = _activated_skills.set(cleaned)
    try:
        yield cleaned
    finally:
        _activated_skills.reset(token)
