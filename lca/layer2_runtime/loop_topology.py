"""LoopTopology 默认实现 —— 宪法 C1 六步闭集。

phase 顺序：perceive → think → act → reflect → remember → stop。
profile 可通过 bundle 装变体，但闭集纪律由宪法约束（本类不做开关）。

seam key 约定：``agent.before_/after_<phase>``；与 HookEvent 枚举的
``pre_/post_`` 命名区分（HookEvent 用于内部触发；seam key 是 6 扩展点
公开契约）。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.protocols.reducer import LoopPhase, LoopPhaseKind, LoopTopology


@dataclass(frozen=True, slots=True)
class _ClosedSetPhase:
    kind: LoopPhaseKind
    pre_hook: str | None
    post_hook: str | None

    @property
    def kind_value(self) -> str:
        return self.kind.value


class ClosedSetTopology(LoopTopology):
    """宪法 C1 六步闭集：CognitiveRuntime._loop 唯一允许的 phase 顺序。"""

    def phases(self) -> tuple[LoopPhase, ...]:
        return _PHASES

    def seam_keys(self) -> tuple[str, ...]:
        """扩展 seam 键全集。

        C1 闭集 6 phase 内 8 个 before/after hook + 2 个跨 phase 生命周期
        seam（``agent.pre_step`` 每步入口；``agent.before_turn_end`` 闭合前）。
        """
        return _PHASE_HOOKS + _LIFECYCLE_SEAMS


_PHASE_HOOKS: tuple[str, ...] = (
    "agent.before_perceive",
    "agent.after_perceive",
    "agent.before_think",
    "agent.after_think",
    "agent.before_act",
    "agent.after_act",
    "agent.before_reflect",
    "agent.after_reflect",
)

_LIFECYCLE_SEAMS: tuple[str, ...] = (
    "agent.pre_step",
    "agent.before_turn_end",
)


_PHASES: tuple[LoopPhase, ...] = (
    _ClosedSetPhase(
        LoopPhaseKind.PERCEIVE,
        "agent.before_perceive",
        "agent.after_perceive",
    ),
    _ClosedSetPhase(
        LoopPhaseKind.THINK,
        "agent.before_think",
        "agent.after_think",
    ),
    _ClosedSetPhase(
        LoopPhaseKind.ACT,
        "agent.before_act",
        "agent.after_act",
    ),
    _ClosedSetPhase(
        LoopPhaseKind.REFLECT,
        "agent.before_reflect",
        "agent.after_reflect",
    ),
    _ClosedSetPhase(LoopPhaseKind.REMEMBER, None, None),
    _ClosedSetPhase(LoopPhaseKind.STOP, None, None),
)


__all__ = ["ClosedSetTopology"]
