"""Reducer Protocol（ADR-0066 / 宪法 C4）。

运行时编排不直接写入状态；所有 ``AgentState`` mutation 必须经
``Reducer`` Protocol 的方法返回新 state。六阶段闭集与执行顺序由
声明式 ``PhaseGraph`` 在编译期验证，不再维护一套未被运行时消费的拓扑协议。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision
from lca.contracts.models.core.terminal_outcome import ResumeCursor, TerminalOutcome


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

    def apply_terminal_outcome(
        self,
        state: AgentState,
        stop: StopDecision,
        *,
        plan_ref: str,
        journal_seq_end: int,
        resume_cursor: ResumeCursor | None = None,
    ) -> TerminalOutcome:
        """Fold terminal state into the sole ``TerminalOutcome`` (ADR-0077 §决策一).

        The Stop phase supplies ``stop``. A paused declarative run additionally
        supplies its already-declared durable ``resume_cursor``. Reducer remains
        the only entity allowed to construct terminal truth; callers provide
        facts, never a pre-built TerminalOutcome (ADR-0077 §决策二).
        """
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

    def apply_paused(self, state: AgentState, snapshot_ref: object) -> AgentState:
        """标记 INPUT_REQUIRED（HIL 等待审批）。"""
        ...
