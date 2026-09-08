"""SkillActivationReducerBridge —— Session facts → reducer 单写 (PR-E)。

ADR-0186 / C4 兑现路径：``SkillActivated`` 事件是 Session 唯一事实轨上的
"激活"事实;reducer 单写必须经由此路径,而不是工具侧直调 reducer。

设计要点(PR-E / 2026-09-08):
- bridge 接收 ``SkillActivated`` 事件,转译为 ``tuple[ActivatedSkill, ...]``,
  调 ``reducer.apply_activation(state, activated)``。
- 幂等:同一 ``skill_id`` 在同 run 内不重复 extend —— 通过 reducer 自身
  的 ``extend`` 语义(append-only) 与 ``ActivatedSkill`` 的 ``skill_id``
  唯一性保证。
- bridge 是 late-binding:运行启动时由 ``CognitiveRuntime.run()`` 装入
  ``reducer`` + ``state_getter``;卸载走 ``dispose()``。
- 不在 Session 事件总线直接订阅,而是从 ``register_activated`` 这条已知
  chokepoint 接出,避免对 Session 总线做无差别订阅。

delete_when(PR-E):
    ``rg "SkillActivationReducerBridge" lca/ = 0`` 且 reducer.apply_activation
    已迁移到 Session fold-only 路径(当前架构下不可达,故本 bridge 退役
    取决于 fold-only 路径是否实施)。
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable

from lca.contracts.models.core.workspace.activation import ActivatedSkill

if TYPE_CHECKING:
    from lca.contracts.models.core.state.state import AgentState
    from lca.contracts.protocols.state.reducer import Reducer


# State accessor: returns the *live* mutable AgentState. Late-bound because
# reducer/reducer-owned state live in the run loop, not at import time.
StateGetter = Callable[[], "AgentState"]


class SkillActivationReducerBridge:
    """把 ``register_activated`` 转译为 ``reducer.apply_activation``。

    注册生命周期:
    - ``install(reducer, state_getter)`` —— run 启动时一次。
    - ``handle(skill_id, name)`` —— 每次 ``register_activated`` 调一次。
    - ``dispose()`` —— run 结束 / 中断时清理,避免悬空引用。

    线程安全:run 内部在 asyncio 单线程内跑,但 import-time / 多 worker 场景
    仍需锁。``_lock`` 是细粒度的临界区,只保护 install/dispose 与 handle 的
    交叉;handle 自身的 reducer 调用由 caller 负责并发语义。
    """

    __slots__ = ("_reducer", "_state_getter", "_lock", "_installed")

    def __init__(self) -> None:
        self._reducer: "Reducer | None" = None
        self._state_getter: StateGetter | None = None
        self._lock = threading.Lock()
        self._installed = False

    def install(
        self,
        *,
        reducer: "Reducer",
        state_getter: StateGetter,
    ) -> None:
        """运行启动时绑定 reducer + state accessor。多次 install 是幂等的(覆盖)。"""
        with self._lock:
            self._reducer = reducer
            self._state_getter = state_getter
            self._installed = True

    def dispose(self) -> None:
        """运行结束清理。dispose 后 handle() 是 no-op。"""
        with self._lock:
            self._reducer = None
            self._state_getter = None
            self._installed = False

    @property
    def installed(self) -> bool:
        return self._installed

    def handle(self, *, skill_id: str, name: str) -> None:
        """``register_activated`` 调用时触发 reducer.apply_activation。

        不在 install 前调用 = no-op(避免 import-time / 测试 fixture 误触发)。
        """
        with self._lock:
            if not self._installed:
                return
            reducer = self._reducer
            state_getter = self._state_getter
        if reducer is None or state_getter is None:
            return
        state = state_getter()
        # reducer.apply_activation 已实现:extend(activated);空 tuple 早返回
        reducer.apply_activation(state, (ActivatedSkill(skill_id=skill_id, name=name),))


# 进程级 singleton —— ``register_activated`` 这条 chokepoint 不持有 run 上下文,
# 所以需要全局可寻址的 bridge。run 启动时 ``install``,run 结束 ``dispose``。
bridge = SkillActivationReducerBridge()


__all__ = ["SkillActivationReducerBridge", "bridge"]