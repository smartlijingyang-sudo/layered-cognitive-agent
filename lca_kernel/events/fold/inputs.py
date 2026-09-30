"""Event decoding / morphism inputs for the fold family.

统一 spine event / SessionEvent / raw dict 三种入口形态,输出 fold core
可消费的归一化视图:

- :func:`_coerce_event` —— header fold 的 ``(category, payload)``
- :func:`_coerce_step_tree_event` —— step-tree fold 的 ``(type, data)``
- :func:`_parse_event` / :func:`_surface_op_of` —— surface fold 的
  :class:`_EventView` + 规范化 ``surfaceOp``
- :data:`SURFACE_EVENT_TYPES` 等 category / type 闭集常量

本模块是纯函数集,无 I/O、无副作用;不依赖任何 fold 结果类型。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeGuard

REQUEST_HEADER_CATEGORY: str = "spine.llm.request.header"
"""fold 识别的事件 category 字符串。

对齐 ADR-0185 §3.3 + §3.5:本模块只识别这一类 spine event,其他
``spine.llm.request.header.assistant`` / ``spine.tool.*`` / ``spine.runtime.*``
等一律 skip。等 PR-1 注册 ``SpineLlmRequestHeaderPayload`` + yaml fields 后,
上游 fold 调用由 publisher 内部 + viewer 接管。
"""


# ── StepTree fold(对齐 DSH turn/step 事件重建)────────────────────────

STEP_START_TYPE: str = "step/start"
"""step 开始事件的 type 字符串。"""

STEP_END_TYPE: str = "step/end"
"""step 结束事件的 type 字符串。"""

TURN_START_TYPE: str = "turn/start"
"""turn 开始事件的 type 字符串。"""

TURN_END_TYPE: str = "turn/end"
"""turn 结束事件的 type 字符串。"""


# ── Surface fold(对齐 DSH foldSurface;ADR-0186 I-SESSION-2)────────────

SURFACE_USER_TYPE: str = "spine.llm.request.header"
"""模型可见 user / prompt 节点的 spine category。

dsh ``user/message`` 的 LCA 对位:header payload 的 ``messages`` 是发给
模型的原文序列,本 fold 只把该事件当作 surface 节点,不展开 messages。
"""

SURFACE_ASSISTANT_TYPE: str = "spine.llm.request.header.assistant"
"""模型可见 assistant 产出节点的 spine category。

dsh ``assistant/message`` 的 LCA 对位。允许 ``sourceEventSeqs=[]``
(空 provider 流);其他 surface 类型在该字段出现时必须非空。
"""

SURFACE_TOOL_RESULT_TYPE: str = "spine.body.tool.execute.end"
"""模型可见 tool 回执节点的 spine category。

dsh ``tool/result`` 的 LCA 对位。replace 只能改 content 类字段
(``outcome`` / ``content`` / ``result``,或 dsh ``message.content[0].content``),
身份字段必须与被替换节点一致。
"""

SURFACE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        SURFACE_USER_TYPE,
        SURFACE_ASSISTANT_TYPE,
        SURFACE_TOOL_RESULT_TYPE,
    }
)
"""可进入模型可见 surface 的 category 闭集。

词表映射(dsh → LCA spine):

- ``user/message`` → ``spine.llm.request.header``
- ``assistant/message`` → ``spine.llm.request.header.assistant``
- ``tool/result`` → ``spine.body.tool.execute.end``

只有这些类型可携带 ``surfaceOp`` / ``sourceEventSeqs``;其它 category
(含 ``turn/start``、``spine.llm.call.*``、dsh 原名)出现这两字段即失败。
"""

_MISSING: object = object()
"""事件信封缺省标记;与显式 ``None`` 区分(``surfaceOp: null`` 是非法值)。"""


@dataclass(frozen=True, slots=True)
class SurfaceReplaceOp:
    """positional replace:用本节点替换 surface 上 ``start``..``end`` 闭区间。

    ``start`` / ``end`` 是当前 surface 上已有节点的 seq,不是 log 下标。
    ``start == end`` 替换单节点。precondition:两者都在 fold 当时的
    ``nodes`` 里且 ``index(start) <= index(end)``。
    """

    op: Literal["replace"]
    start: int
    end: int


SurfaceOp = Literal["append"] | SurfaceReplaceOp
"""surface 进入方式:``append`` 接到尾部,或 :class:`SurfaceReplaceOp`。"""


@dataclass(frozen=True, slots=True)
class _EventView:
    """fold 内部统一信封;不对外暴露。"""

    type: str
    seq: object
    data: Mapping[str, Any]
    surface_op: object
    source_event_seqs: object
    has_surface_op: bool
    has_source_event_seqs: bool


def isSurfaceEligibleType(type_: str) -> bool:  # noqa: N802 (dsh parity)
    """``type_`` 是否属于 :data:`SURFACE_EVENT_TYPES`。"""
    return type_ in SURFACE_EVENT_TYPES


def isSurfaceEvent(event: Any) -> bool:  # noqa: N802 (dsh parity)
    """事件是否已带 surface 标记:类型合格且 ``surfaceOp`` 字段存在。"""
    view = _parse_event(event)
    return isSurfaceEligibleType(view.type) and view.has_surface_op


def isAppendSurfaceEvent(event: Any) -> bool:  # noqa: N802 (dsh parity)
    """surface 事件且 ``surfaceOp == 'append'``(本节点从未作为 replace 副本)。"""
    if not isSurfaceEvent(event):
        return False
    return _parse_event(event).surface_op == "append"


def isReplacementSurfaceEvent(event: Any) -> bool:  # noqa: N802 (dsh parity)
    """surface 事件且 ``surfaceOp`` 不是 ``append``(replace 进入 surface)。"""
    if not isSurfaceEvent(event):
        return False
    return _parse_event(event).surface_op != "append"


def _field(event: Any, *names: str) -> object:
    """从 Mapping 键或对象属性取信封字段;都没有返回 ``_MISSING``。"""
    if isinstance(event, Mapping):
        for name in names:
            if name in event:
                return event[name]
        return _MISSING
    for name in names:
        if hasattr(event, name):
            return getattr(event, name)
    return _MISSING


def _parse_event(event: Any) -> _EventView:
    """把 SessionEvent / spine dict / 任意信封归一成 :class:`_EventView`。

    字段别名(LCA snake_case 与 dsh camelCase 都认,读到即停):

    - type: ``type`` / ``category``
    - data: ``data`` / ``payload``
    - surfaceOp: ``surfaceOp`` / ``surface_op``
    - sourceEventSeqs: ``sourceEventSeqs`` / ``source_event_seqs``
    """
    raw_type = _field(event, "type", "category")
    event_type = "" if raw_type is _MISSING else str(raw_type)
    seq = _field(event, "seq")
    raw_data = _field(event, "data", "payload")
    data: Mapping[str, Any] = raw_data if isinstance(raw_data, Mapping) else {}
    surface_op = _field(event, "surfaceOp", "surface_op")
    sources = _field(event, "sourceEventSeqs", "source_event_seqs")
    return _EventView(
        type=event_type,
        seq=None if seq is _MISSING else seq,
        data=data,
        surface_op=surface_op,
        source_event_seqs=sources,
        has_surface_op=surface_op is not _MISSING and surface_op is not None,
        has_source_event_seqs=sources is not _MISSING and sources is not None,
    )


def _is_event_seq(value: object) -> TypeGuard[int]:
    """非负 int;拒绝 bool(``True`` 是 ``int`` 子类)。"""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _as_replace_op(value: object) -> SurfaceReplaceOp | None:
    """把运行时值收成 :class:`SurfaceReplaceOp`;形状不对返回 None。"""
    if isinstance(value, SurfaceReplaceOp):
        if _is_event_seq(value.start) and _is_event_seq(value.end):
            return value
        return None
    if not isinstance(value, Mapping) or set(value.keys()) != {"op", "start", "end"}:
        return None
    if value.get("op") != "replace":
        return None
    start, end = value["start"], value["end"]
    if not (_is_event_seq(start) and _is_event_seq(end)):
        return None
    return SurfaceReplaceOp(op="replace", start=start, end=end)


def _surface_op_of(view: _EventView) -> SurfaceOp | None:
    """校验类型与 marker 的配对,返回规范化 ``surfaceOp``。

    失败语义(``ValueError``):非合格类型携带 marker / 合格类型缺 marker /
    marker 既不是 ``append`` 也不是三字段 replace 对象。
    """
    if not isSurfaceEligibleType(view.type):
        if view.has_surface_op:
            raise ValueError(
                f'session event "{view.type}" is not surface-eligible and cannot carry surfaceOp'
            )
        if view.has_source_event_seqs:
            raise ValueError(
                f'session event "{view.type}" is not surface-eligible '
                "and cannot carry sourceEventSeqs"
            )
        return None
    if not view.has_surface_op:
        # LCA 双用:``spine.llm.request.header`` 可无 surfaceOp 仅作 request_header fold,
        # 带 surfaceOp 才进入 surface 序列(DSH 的 user/message 与 request/header 分立)。
        return None
    op = view.surface_op
    if op == "append":
        return "append"
    if op is None or not isinstance(op, (Mapping, SurfaceReplaceOp)):
        raise ValueError(f'session event "{view.type}" carries an invalid surfaceOp')
    parsed = _as_replace_op(op)
    if parsed is None:
        raise ValueError(f'session event "{view.type}" carries an invalid replace surfaceOp')
    return parsed


def _coerce_event(event: Any) -> tuple[str, Mapping[str, Any]] | None:
    """统一 spine event 形态。

    支持三种入口(纯函数隔离 IO):

    - :class:`SpineEventRecord`(``category`` + ``payload`` 属性)
    - ``Mapping``(``category`` / ``payload`` 键;``category`` 可缺省,缺省视为
      ``spine.llm.request.header``,便于直接传 raw dict fixture)

    返回 ``(category, payload)``;不是 fold 目标则 raise 给调用方处理
    (本函数不静默吞,类型不匹配显式失败)。
    """
    if hasattr(event, "category") and hasattr(event, "payload"):
        category = str(event.category)
        payload = event.payload
        return category, payload if isinstance(payload, Mapping) else {}
    if isinstance(event, Mapping):
        category_val = event.get("category")
        if category_val is None:
            # 缺省视为 fold target:parity 适配 raw dict fixture
            payload_val = event.get("payload") or {}
            return REQUEST_HEADER_CATEGORY, payload_val if isinstance(payload_val, Mapping) else {}
        return str(category_val), event.get("payload") or {}
    return None


def _coerce_step_tree_event(event: Any) -> tuple[str, Mapping[str, Any]] | None:
    """统一 step tree fold 的事件形态。

    支持三种入口:

    - :class:`SessionEvent`(``type`` + ``data`` 属性)
    - ``Mapping``(``type`` / ``data`` 键)
    - :class:`SpineEventRecord`(``category`` + ``payload``;不识别则 None)

    返回 ``(type, data)``;不是 step tree 目标则返回 None。
    """
    if hasattr(event, "type") and hasattr(event, "data") and not hasattr(event, "category"):
        return str(event.type), event.data if isinstance(event.data, Mapping) else {}
    if isinstance(event, Mapping):
        event_type = event.get("type")
        if event_type is not None:
            return str(event_type), event.get("data") or {}
        return None
    return None
