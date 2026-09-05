"""SessionStatsUnit —— ``session_stats`` 投影单元（DSH session-stats 的 LCA 裁剪形）。

纯 fold：``turn.started/ended.v1``、``step.started/ended.v1``、
``model.requested/completed.v1`` 的计数与回合墙钟时间。墙钟只用
``event.time`` 差值（时间经事件注入，单元无 wall clock 直读，
确定性不变量 C8）；``wall_ms_by_turn`` 以 ``str(turn)`` 为键，
保持纯 JSON 检查点的序列化往返形状不变。

与 DSH ``sessionStats`` 的裁剪偏差：

- DSH 折 ``llmMs`` / ``toolMs`` / ``ttftMs`` / ``decodeMs`` /
  ``decodeTokens``，源自 ``step/*`` + ``assistant/chunk`` +
  ``assistant/message`` + ``tool/call|result``；LCA Session 词表不含
  ``tool.*.v1``（工具事实归 Journal 平面，见
  ``docs/specs/session-event-pipeline-spec.md`` §5）且无流式帧 /
  首 token 边界（``model.completed.v1.usage`` 无结算消息边界），
  故时间裁剪到回合边界墙钟（``turn.started → turn.ended``）。
- ``turns`` 计 ``turn.started.v1``（进入的回合）；``steps`` 计
  ``step.started.v1``（进入的步骤）；``step.ended.v1`` /
  ``model.completed.v1`` 在裁剪态下不改变总量（返回同一引用）。
- ``last_turn_end_seq`` 记最后一条 ``turn.ended.v1`` 的 seq（空日志 -1）。
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca_kernel.events.session import SessionEvent

_log = structlog.get_logger(__name__)

__all__ = ["Config", "SessionStatsUnit", "setup"]

_TURN_STARTED = "turn.started.v1"
_TURN_ENDED = "turn.ended.v1"
_STEP_STARTED = "step.started.v1"
_MODEL_REQUESTED = "model.requested.v1"


def _turn_of(event: SessionEvent) -> int | None:
    """事件 payload 的非负整数 ``turn``；缺失 / 非法返回 ``None``。"""
    turn = event.data.get("turn")
    if isinstance(turn, int) and not isinstance(turn, bool) and turn >= 0:
        return turn
    return None


class SessionStatsUnit:
    """回合/步骤/模型计数与回合墙钟的纯 fold 单元。

    ``view`` 出口为总量（不含宿主内部边界字段）；状态为纯 JSON，
    满足持久化投影缓存前提。
    """

    key: str = "session_stats"
    state_version: int = 1

    def init(self, header: Any) -> dict[str, Any]:
        """空日志状态：全部总量归零、无进行中回合边界。

        ``header`` 本单元不用（保留契约入参）。
        """
        del header
        return {
            "turns": 0,
            "steps": 0,
            "model_requests": 0,
            "last_turn_end_seq": -1,
            "wall_ms_by_turn": {},
            "open_turn": None,
        }

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        """纯转移；无关事件（含 ``step.ended`` / ``model.completed``）返回同一引用。"""
        event_type = event.type
        if event_type == _TURN_STARTED:
            return self._apply_turn_started(state, event)
        if event_type == _TURN_ENDED:
            return self._apply_turn_ended(state, event)
        if event_type == _STEP_STARTED:
            return {**state, "steps": state["steps"] + 1}
        if event_type == _MODEL_REQUESTED:
            return {**state, "model_requests": state["model_requests"] + 1}
        return state

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        """完整当前值：总量（不含 ``open_turn`` 边界字段）。"""
        return {
            "turns": state["turns"],
            "steps": state["steps"],
            "model_requests": state["model_requests"],
            "last_turn_end_seq": state["last_turn_end_seq"],
            "wall_ms_by_turn": dict(state["wall_ms_by_turn"]),
        }

    # ── 内部 ────────────────────────────────────────────────────────

    def _apply_turn_started(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        turn = _turn_of(event)
        open_turn = {"turn": turn, "start_time": event.time} if turn is not None else None
        return {**state, "turns": state["turns"] + 1, "open_turn": open_turn}

    def _apply_turn_ended(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        turn = _turn_of(event)
        next_state = {**state, "last_turn_end_seq": event.seq}
        open_turn = state["open_turn"]
        if turn is not None and isinstance(open_turn, dict) and open_turn["turn"] == turn:
            wall_ms = max(0, event.time - open_turn["start_time"])
            next_state["wall_ms_by_turn"] = {**state["wall_ms_by_turn"], str(turn): wall_ms}
            next_state["open_turn"] = None
        return next_state


class Config(BaseModel):
    """统计单元包无配置项；拒绝未知键防声明漂移。"""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca.plugins.session.session_stats",
    provides=["session.projection.session_stats"],
    requires=["session.projections"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "session_stats 投影单元包（模块②，DSH session-stats 的 LCA 裁剪形）："
        "折 turn/step/model 事件为计数与回合墙钟时间（event.time 差值，"
        "无 wall clock 直读），经 session.projections capability 注册到"
        "投影注册表。单元纯 fold，无副作用。"
    ),
    test_suite="tests/plugins/session/test_session_stats.py",
    functional_group=FunctionalGroup.G3_FACTS,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G3_FACTS),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
    ),
    ownership=OwnershipDeclaration(
        reads=("session.projections",),
        emits=(),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """单元包 boot：向注册表注册 :class:`SessionStatsUnit`。

    ``session.projections`` 经 ``soft_get`` 取（可选注册，对齐 DSH
    ``ctx.inject(['sessionProjections'], ...)`` 形态）：缺席时 no-op +
    记日志，capability 仍提供，测试可在装载注册表后手动注册。
    """
    del config
    unit = SessionStatsUnit()
    ctx.provide("session.projection.session_stats", unit)
    registry = ctx.soft_get("session.projections")
    if registry is None:
        _log.info("session.stats.no_registry", id="lca.plugins.session.session_stats")
        return
    registry.register(unit)
