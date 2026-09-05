"""TurnOutlineUnit —— ``turn_outline`` 投影单元（DSH session-turn-outline 的 LCA 形态）。

纯 fold：``turn.started.v1``（seq 锚点）+ ``message.accepted.v1``（首条
prompt 预览，截断 80 字符）+ ``turn.ended.v1``（``ended`` 落位）→
rail 列表 ``[{turn, start_seq, prompt_preview, ended}]``。

``turn.started`` —— 而非 prompt 的 ``message.accepted`` —— 锚定每个条目，
因为它的 seq 是跳转的 load-through 目标：回合边界先于该回合的 prompt 与
步骤入日志，按该 seq 回读的窗口能覆盖整个回合。``start_seq`` 即该
``turn.started`` 事件的 seq。

与 DSH ``turnOutline`` 的裁剪偏差：

- DSH 折 prompt + response 双预览（``user/message`` 与
  ``assistant/message`` 内容块），rail 条目为
  ``{turn, seq, prompt, response}``；LCA Session 词表的模型表面是
  ``message.accepted.v1``（payload 只带 ``message_id`` / ``role`` /
  ``content_ref``），无独立 assistant 结算文本块，故裁剪为单一
  ``prompt_preview`` + ``ended`` 布尔。
- DSH 有 ``draft``（最新 assistant 文本，``turn/end`` 提交）以在
  ``turns`` 数组身份不变的前提下压住变更推送；LCA 无 response 面，
  状态只有 ``turns``，无需 draft 字段。
- prompt 取 ``message.accepted.v1`` 的 ``content_ref``（``role == "user"``，
  对齐 DSH ``source.kind == 'user'``）；同回合后续用户消息保留首条预览。
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

__all__ = ["Config", "TurnOutlineUnit", "setup"]

_TURN_STARTED = "turn.started.v1"
_TURN_ENDED = "turn.ended.v1"
_MESSAGE_ACCEPTED = "message.accepted.v1"
_ROLE_USER = "user"

PROMPT_PREVIEW_LIMIT = 80
"""prompt 预览预算：一条 rail 卡片行，超长截断并附省略号。"""


def _turn_of(event: SessionEvent) -> int | None:
    """事件 payload 的非负整数 ``turn``；缺失 / 非法返回 ``None``。"""
    turn = event.data.get("turn")
    if isinstance(turn, int) and not isinstance(turn, bool) and turn >= 0:
        return turn
    return None


def _preview(text: str, limit: int) -> str:
    """折叠空白、两端裁剪，超长按 ``limit - 1`` 截断并附省略号（总长 ≤ limit）。

    对齐 DSH ``preview()`` 的归一化语义：空白压缩成单空格，裁剪后
    ``…`` 结尾；结果永不超过 ``limit`` 字符。
    """
    normalized = " ".join(text.split())
    if len(normalized) > limit - 1:
        return normalized[: limit - 1].rstrip() + "…"
    return normalized


class TurnOutlineUnit:
    """回合 rail（turn + seq 锚点 + prompt 预览 + 结束位）的纯 fold 单元。

    ``view`` 出口为 ``turns`` 列表（每个条目是一致读切下的完整值）；
    状态为纯 JSON，满足持久化投影缓存前提。条目顺序按 ``turn`` 严格递增。
    """

    key: str = "turn_outline"
    state_version: int = 1

    def init(self, header: Any) -> dict[str, Any]:
        """空日志状态：空 rail。``header`` 本单元不用（保留契约入参）。"""
        del header
        return {"turns": []}

    def apply(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        """纯转移；无关事件返回同一引用（``==`` 闸门压制下游）。

        ``turn.started`` 建条目（``turn`` 不推进则保序复用）；
        ``message.accepted``（``role == user``）填首条空 ``prompt_preview``；
        ``turn.ended`` 把匹配 ``turn`` 的条目 ``ended`` 落 ``True``。
        """
        event_type = event.type
        if event_type == _TURN_STARTED:
            return self._apply_turn_started(state, event)
        if event_type == _MESSAGE_ACCEPTED:
            return self._apply_message_accepted(state, event)
        if event_type == _TURN_ENDED:
            return self._apply_turn_ended(state, event)
        return state

    def view(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """完整当前值：rail 列表（拷贝，避免外发改动内部状态）。"""
        return [dict(entry) for entry in state["turns"]]

    # ── 内部 ────────────────────────────────────────────────────────

    def _apply_turn_started(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        turn = _turn_of(event)
        if turn is None:
            return state
        turns = state["turns"]
        last = turns[-1] if turns else None
        # 顺序守卫：不推进 turn 的边界保序，重试回合的预览落在既有条目上。
        if last is not None and turn <= last["turn"]:
            return state
        entry = {"turn": turn, "start_seq": event.seq, "prompt_preview": "", "ended": False}
        return {"turns": [*turns, entry]}

    def _apply_message_accepted(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        # 只有最新回合还可能在等它的开场用户 prompt；同回合后续用户消息保留首条预览。
        if event.data.get("role") != _ROLE_USER:
            return state
        turns = state["turns"]
        last = turns[-1] if turns else None
        if last is None or last["prompt_preview"] != "":
            return state
        content_ref = event.data.get("content_ref")
        if not isinstance(content_ref, str):
            return state
        prompt = _preview(content_ref, PROMPT_PREVIEW_LIMIT)
        if prompt == "":
            return state
        return {"turns": [*turns[:-1], {**last, "prompt_preview": prompt}]}

    def _apply_turn_ended(self, state: dict[str, Any], event: SessionEvent) -> dict[str, Any]:
        turn = _turn_of(event)
        if turn is None:
            return state
        turns = state["turns"]
        changed = False
        next_turns: list[dict[str, Any]] = []
        for entry in turns:
            if entry["turn"] == turn and not entry["ended"]:
                next_turns.append({**entry, "ended": True})
                changed = True
            else:
                next_turns.append(entry)
        return {"turns": next_turns} if changed else state


class Config(BaseModel):
    """回合 outline 单元包无配置项；拒绝未知键防声明漂移。"""

    model_config = {"extra": "forbid"}


@plugin(
    id="lca.plugins.session.session_turn_outline",
    provides=["session.projection.session_turn_outline"],
    requires=["session.projections"],
    layer="L2",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "turn_outline 投影单元包（模块②，DSH session-turn-outline 的 LCA "
        "形态）：折 turn.started(seq 锚点) + message.accepted(首条 prompt "
        "预览, 截断 80 字符) + turn.ended → rail 列表 [{turn, start_seq, "
        "prompt_preview, ended}]，经 session.projections capability 注册到"
        "投影注册表。单元纯 fold，无副作用。"
    ),
    test_suite="tests/plugins/session/test_session_turn_outline.py",
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
    """单元包 boot：向注册表注册 :class:`TurnOutlineUnit`。

    ``session.projections`` 经 ``soft_get`` 取（可选注册，对齐 DSH
    ``ctx.inject(['sessionProjections'], ...)`` 形态）：缺席时 no-op +
    记日志，capability 仍提供，测试可在装载注册表后手动注册。
    """
    del config
    unit = TurnOutlineUnit()
    ctx.provide("session.projection.session_turn_outline", unit)
    registry = ctx.soft_get("session.projections")
    if registry is None:
        _log.info(
            "session.turn_outline.no_registry",
            id="lca.plugins.session.session_turn_outline",
        )
        return
    registry.register(unit)
