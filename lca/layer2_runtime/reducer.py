"""DefaultReducer —— ADR-0066 的 boot-time 默认 Reducer 实现。

迁移期保留 mutable AgentState 的写法（与既有测试夹具兼容），但所有
mutation 集中在此模块；``CognitiveRuntime._loop`` 不再直接写 state。
"""

from __future__ import annotations

from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.core.stop import StopDecision
from lca.contracts.protocols.reducer import Reducer


class DefaultReducer(Reducer):
    """Reducer Protocol 默认实现（C4 单一写）。

    方法语义：
    - 全部以新 state 形式返回（虽然 AgentState 当前为 mutable dataclass，
      但本类把 mutation 集中在同一文件，未来 AgentState 转 frozen 后只
      改这一处）。
    - 每个方法是纯函数（除 await 内 yield）；无 side effect。
    """

    def apply_step_advanced(self, state: AgentState, step: int) -> AgentState:
        state.step = step
        state.budget.used_steps = step
        return state

    def apply_perception(self, state: AgentState, manifest: ContextManifest) -> AgentState:
        """fold ContextManifest 到 state。

        当前 Hub 已经通过 perceive_state 模块写入 current_manifest 和 gate_decided。
        Reducer 追加 manifest_digest 到 state.extra 作为 idempotency token
        ——用于 replay / cache 校验。
        """
        state.extra["manifest_digest"] = manifest.digest
        return state

    def apply_turn(self, state: AgentState, turn: Turn) -> AgentState:
        state.history.append(turn)
        return state

    def apply_activation(
        self, state: AgentState, activated: tuple[ActivatedSkill, ...]
    ) -> AgentState:
        if not activated:
            return state
        state.activated_skills.extend(activated)
        return state

    def apply_memory(self, state: AgentState, writes: object) -> AgentState:
        """fold MemoryWriteSet 到 state（无副作用版本）。

        Memory 写入由 Memory 协议自身负责（``memory.propose`` /
        ``memory.commit``）；reducer 不直接动 memory 层。本方法为 seam
        完整性保留——plugin 可注入 reducer 在 commit 后做衍生 fold
        （例如 budget.used_tokens 累计）。
        """
        return state

    def apply_stop(self, state: AgentState, stop: StopDecision) -> AgentState:
        if stop.status is not None:
            state.status = stop.status
        if stop.final_output is not None:
            state.final_output = stop.final_output
        return state

    def apply_error(self, state: AgentState, error: BaseException) -> AgentState:
        state.status = TaskStatus.FAILED
        state.last_error = repr(error)
        return state

    def apply_paused(self, state: AgentState, snapshot_ref: object) -> AgentState:
        state.status = TaskStatus.INPUT_REQUIRED
        return state


__all__ = ["DefaultReducer"]
