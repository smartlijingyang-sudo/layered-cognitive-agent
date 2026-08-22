"""Reducer 与 LoopTopology Protocol（ADR-0066 / 宪法 C4）。

`_loop` 是编排者，不是 state 写者。所有 AgentState mutation 必须经
``Reducer`` Protocol 的方法返回新 state。``LoopTopology`` Protocol
声明闭集 phase 顺序（宪法 C1 六步），profile 可通过 bundle 装变体。
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision


@runtime_checkable
class Reducer(Protocol):
    """纯函数 reducer：所有 state mutation 集中此 seam（C4 兑现）。

    每个方法返回新 AgentState，不原地修改。``DefaultReducer`` 是
    boot-time 默认实现；profile 通过 ``ctx.provide("reducer", ...)`` 注入
    自替换（保留 v3 §3.5.3 的「Reducer-as-Plugin」精神）。
    """

    def apply_step_advanced(self, state: AgentState, step: int) -> AgentState:
        """更新 ``state.step`` 与 ``state.budget.used_steps``。"""
        ...

    def apply_perception(self, state: AgentState, manifest: ContextManifest) -> AgentState:
        """fold ``ContextManifest`` 到 state（C3 唯一事实源）。"""
        ...

    def apply_turn(self, state: AgentState, turn: Turn) -> AgentState:
        """追加 ``Turn`` 到 ``state.history``。"""
        ...

    def apply_skill_route(self, state: AgentState, active_template: str | None) -> AgentState:
        """fold ``SkillRouter.route(state)`` 的 active_template 到 state。

        ADR-0066 C4：所有 state mutation 集中此 seam；ModularBrain 不再直接
        写 ``state.active_template``（PR-4 think.guard 原子化迁移）。
        ``active_template`` 是 SkillRouter.route() 返回的 prompt 模板名，
        Reasoner 在生成 thought 时读取；空 = 使用 default template。
        """
        ...

    def apply_activation(
        self, state: AgentState, activated: tuple[ActivatedSkill, ...]
    ) -> AgentState:
        """同步 ``state.activated_skills``（PR5 helper 升格）。"""
        ...

    def apply_memory(
        self,
        state: AgentState,
        writes: object,
    ) -> AgentState:
        """fold ``MemoryWriteSet`` 到 state（split 自原 ``Memory.update``）。"""
        ...

    def apply_stop(self, state: AgentState, stop: StopDecision) -> AgentState:
        """fold ``StopDecision`` 到 state.final_output / state.status。"""
        ...

    def apply_error(self, state: AgentState, error: BaseException) -> AgentState:
        """标记 FAILED 并写入 ``state.last_error``。"""
        ...

    def apply_resume(
        self,
        state: AgentState,
        input_value: object | None,
        turn: Turn | None,
    ) -> AgentState:
        """恢复已加载状态；可选地折叠人工输入对应的 ``Turn``。"""
        ...

    def apply_artifact_closure(self, state: AgentState, closure: str) -> AgentState:
        """折叠交付物闭合文本并在仍工作时标记完成。"""
        ...

    def apply_paused(self, state: AgentState, snapshot_ref: object) -> AgentState:
        """标记 INPUT_REQUIRED（HIL 等待审批）。"""
        ...


class LoopPhaseKind(Enum):
    """Loop topology phase 枚举（宪法 C1 闭集）。"""

    PERCEIVE = "perceive"
    THINK = "think"
    ACT = "act"
    REFLECT = "reflect"
    REMEMBER = "remember"
    STOP = "stop"


class LoopPhase(Protocol):
    """单 phase 声明：kind + hook 名 + 触发位置（前/后）。"""

    @property
    def kind(self) -> LoopPhaseKind: ...

    @property
    def pre_hook(self) -> str | None:
        """phase 入口前的 hook 名；None 表示不触发。"""
        ...

    @property
    def post_hook(self) -> str | None:
        """phase 出口后的 hook 名；None 表示不触发。"""
        ...


class LoopTopology(Protocol):
    """声明 Loop 闭集 phase 顺序（ADR-0066）。

    默认实现 ``ClosedSetTopology`` 返回 C1 六步；profile 通过 bundle 装
    变体（如 PR6.D.5 finalize hook 扩展不破闭集）。
    """

    def phases(self) -> tuple[LoopPhase, ...]:
        """C1 闭集六 phase。"""
        ...

    def seam_keys(self) -> tuple[str, ...]:
        """扩展 seam 键全集（含跨 phase 生命周期 seam）。"""
        ...
