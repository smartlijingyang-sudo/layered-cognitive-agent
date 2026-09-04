"""Header fold — 从 spine.jsonl 重建 effective request header(ADR-0185 PR-0)。

对齐 deepseek-harness ``packages/core/session/src/request-header.ts`` 的
``canonicalHeader`` / ``headerEquals`` / ``sameSchema`` / ``foldRequestHeader``
语义;实现细节独立。本模块:

- 是纯函数集,无 I/O,无 ``print`` / ``logging`` / ``datetime.now`` 等副作用
- 与 PR-1 / PR-2 的 ``SpineLlmRequestHeaderPayload`` 解耦:仅消费
  :class:`SpineEventRecord` 的 ``category`` + ``payload`` dict,fields 由 yaml
  schema 在 PR-1 锁死
- 不依赖具体 LLM/Reasoner/Brain/Body/SafeExecutor:只读 ``SpineEventRecord``
  形态的事件流,任何上游(``<run_id>.spine.jsonl`` 重放、sub-batch 增量 fold、
  viewer 离线重建)都走同一路径

设计原则(ADR-0185 §3.4 + §3.5):

1. **canonicalHeader** — 空 ``system`` / 空 ``adapter_defaults`` / 空 ``tools``
   字段归一为 absent;fold / 比较 / 落盘用同一种表示。匹配 dsh 行为。
2. **headerEquals** — 字节级判等;``config`` 字段逐字段比对(对齐 dsh
   ``callConfigEquals``)、``tools`` 列表按 JSON 序列化对位比较(顺序敏感),
   ``system`` 字符串严格等。
3. **foldRequestHeader** — 单次走完事件流,保留最近一条 ``spine.llm.request.header``
   的 canonical 形态;``from_`` 续接上次 fold 结果,``step_id`` 限定 fold
   范围(对齐 ADR-0185 §3.4 dsh 对位)。
4. **foldSurface** — 单次走完事件流,按 ``surfaceOp`` append / replace 重建
   当前模型可见节点序列(ADR-0186 I-SESSION-2;对齐 dsh
   ``packages/core/session/src/surface.ts`` ``foldSurface``)。词表是 LCA
   spine / model-visible category,不是 dsh ``user/message`` 三件套。

不动 production 行为:无 ``Bus.publish``、无 sink 写入、无 EventBus 内部状态;
仅作为 viewer / explain / replay / debug-run 的离线重建函数。

delete-when:N/A(纯加法,后续 PR-2 publisher fold 状态、PR-3 viewer 重建、
PR-4 删旁路文件都依赖本模块做语义锚点)。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

REQUEST_HEADER_CATEGORY: str = "spine.llm.request.header"
"""fold 识别的事件 category 字符串。

对齐 ADR-0185 §3.3 + §3.5:本模块只识别这一类 spine event,其他
``spine.llm.request.header.assistant`` / ``spine.tool.*`` / ``spine.runtime.*``
等一律 skip。等 PR-1 注册 ``SpineLlmRequestHeaderPayload`` + yaml fields 后,
上游 fold 调用由 publisher 内部 + viewer 接管。
"""


@dataclass(frozen=True, slots=True)
class EpochHeader:
    """单次 LLM 调用的有效 header(对齐 dsh ``EpochHeader``)。

    字段语义对齐 dsh ``packages/core/session/src/types.ts`` ``EpochHeader``
    形态:

    - ``config`` — call config(provider / model / reasoning_effort / 采样标量)
    - ``adapter_defaults`` — adapter 实体化的有效字段标记
      (``reasoning_effort`` / ``max_tokens`` 哪几个由 adapter 决定)
    - ``system`` — 渲染后的 system prompt 原文;空字符串归一为 absent
    - ``tools`` — 装配的工具 schema 序列;空序列归一为 absent

    四字段均允许 ``None`` / 空,语义由 :func:`canonicalHeader` 归一化后单点表示
    决定。frozen + slots 保证 ``headerEquals`` / ``fold`` 不被原地改污染。
    """

    config: Mapping[str, Any] | None = None
    adapter_defaults: Mapping[str, Any] | None = None
    system: str | None = None
    tools: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)


def canonicalHeader(header: EpochHeader) -> EpochHeader:  # noqa: N802 (dsh parity)
    """归一 ``EpochHeader`` 到 canonical 形态(对齐 dsh ``canonicalHeader``)。

    规则:

    - 空字符串 ``system`` → ``None``
    - 空 ``tools`` 序列 → ``()``
    - ``config`` 永远保留(无空判定:``config`` 是 header 的最小可识别单元)
    - ``adapter_defaults`` 仅在 ``reasoning_effort == True`` 或
      ``max_tokens == True`` 时保留;否则 absent(对齐 dsh
      ``canonicalHeader`` spread 行为)

    返回新对象,不修改入参;``frozen`` 语义保证 caller 持有引用不变。
    """
    system = header.system if header.system else None
    tools = header.tools if header.tools else ()

    adapter_defaults_raw = header.adapter_defaults
    if adapter_defaults_raw and (
        adapter_defaults_raw.get("reasoning_effort") is True
        or adapter_defaults_raw.get("max_tokens") is True
    ):
        adapter_defaults: Mapping[str, Any] | None = adapter_defaults_raw
    else:
        adapter_defaults = None

    return EpochHeader(
        config=header.config,
        adapter_defaults=adapter_defaults,
        system=system,
        tools=tools,
    )


def _sameSchema(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:  # noqa: N802 (dsh parity)
    """工具 schema 字节级判等(对齐 dsh ``sameSchema``)。

    用 ``json.dumps(..., sort_keys=True)`` 做 canonical JSON 字符串比对;
    同一工具经同一路径装配,字段名顺序漂移不影响比对结果。
    """
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def headerEquals(a: EpochHeader, b: EpochHeader) -> bool:  # noqa: N802 (dsh parity)
    """canonical header 字段级判等(对齐 dsh ``headerEquals``)。

    逐字段比对:

    - ``config`` — 逐键比对(provider / model / reasoning_effort / temperature /
      max_tokens / stop 等),stop 列表元素逐一对位
    - ``adapter_defaults`` — ``reasoning_effort`` / ``max_tokens`` 标记位比对
    - ``system`` — 字符串严格等
    - ``tools`` — 长度等 + 元素顺序敏感 + 元素级 ``_sameSchema`` 字节级比对

    入参未归一时返回值仍正确(短字段按 ``None`` / 空 tuple 对位);但生产
    调用方应先 ``canonicalHeader`` 再比,与 dsh 实现一致。
    """
    if a.config != b.config:
        return False
    if a.adapter_defaults != b.adapter_defaults:
        return False
    if a.system != b.system:
        return False
    at = a.tools or ()
    bt = b.tools or ()
    if len(at) != len(bt):
        return False
    return all(_sameSchema(left, right) for left, right in zip(at, bt, strict=True))


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


def _state_from_payload(payload: Mapping[str, Any]) -> EpochHeader:
    """从 ``spine.llm.request.header`` payload 还原 ``EpochHeader``。

    PR-1 前字段未类型化锁死;本函数对 payload 做最小字段映射:

    - ``config`` → ``EpochHeader.config``
    - ``adapter_defaults`` → ``EpochHeader.adapter_defaults``
    - ``system`` → ``EpochHeader.system``
    - ``tools`` → ``EpochHeader.tools``

    不识别字段(``messages`` / ``manifest`` / ``reason`` 等)本函数不读,
    由 PR-1 payload typing 锁字段后接入。
    """
    config_val = payload.get("config") if "config" in payload else None
    adapter_defaults_val = (
        payload.get("adapter_defaults") if "adapter_defaults" in payload else None
    )
    system_val = payload.get("system") if "system" in payload else None
    tools_val = payload.get("tools") if "tools" in payload else None

    if isinstance(config_val, Mapping):
        config: Mapping[str, Any] | None = config_val
    elif config_val is None:
        config = None
    else:
        config = None  # type mismatch → absent(对齐 dsh 容忍度)

    if isinstance(adapter_defaults_val, Mapping):
        adapter_defaults: Mapping[str, Any] | None = adapter_defaults_val
    elif adapter_defaults_val is None:
        adapter_defaults = None
    else:
        adapter_defaults = None

    if isinstance(system_val, str):
        system: str | None = system_val
    elif system_val is None:
        system = None
    else:
        system = str(system_val)

    if isinstance(tools_val, (list, tuple)):
        coerced = tuple(t for t in tools_val if isinstance(t, Mapping))
        tools: tuple[Mapping[str, Any], ...] = coerced
    elif tools_val is None:
        tools = ()
    else:
        tools = ()

    return EpochHeader(
        config=config,
        adapter_defaults=adapter_defaults,
        system=system,
        tools=tools,
    )


def foldRequestHeader(  # noqa: N802 (dsh parity)
    events: Iterable[Any],
    *,
    step_id: str | None = None,
    from_: EpochHeader | None = None,
) -> EpochHeader | None:
    """离线 fold — 扫一遍事件流,返回最近生效的 canonical header(对齐 dsh)。

    语义对齐 dsh ``foldRequestHeader(events, from)`` + ADR-0185 §3.4 §3.5:

    - ``events`` 可前缀(增量 fold)或全量;非 ``spine.llm.request.header`` 一律跳过
    - ``from_`` 续接上次 fold 结果(避免每次全量扫,viewer 走增量路径)
    - ``step_id`` 非空时只 fold 该 ``step_id`` 的事件;为空则 fold 整条流
    - 返回最后一条 header 的 canonical 形态;空流返回 ``from_`` 或 ``None``

    入参形态(spine event / raw dict)由 :func:`_coerce_event` 统一;不识别
    类型显式 ``None``(不抛,与 dsh TS 行为对齐:未知形态跳过)。

    与 dsh 实现差异(显式列出):

    - dsh 直接读 ``event.data.header`` 字段;LCA 走 ``payload``(SpineEventRecord
      字节布局是 ``payload`` 而非 ``data``,对齐 ADR-0183 §3.5 SSOT)
    - dsh 不支持 ``step_id`` 过滤;LCA 加这一维(PR-3 explain / viewer 按 step
      重建 header 需要)
    """
    state = from_
    for event in events:
        coerced = _coerce_event(event)
        if coerced is None:
            continue
        category, payload = coerced
        if category != REQUEST_HEADER_CATEGORY:
            continue
        if step_id is not None:
            event_step_id = payload.get("step_id") if isinstance(payload, Mapping) else None
            if event_step_id != step_id:
                continue
        state = canonicalHeader(_state_from_payload(payload))
    return state


# ── StepTree fold(对齐 DSH turn/step 事件重建)────────────────────────

STEP_START_TYPE: str = "step/start"
"""step 开始事件的 type 字符串。"""

STEP_END_TYPE: str = "step/end"
"""step 结束事件的 type 字符串。"""

TURN_START_TYPE: str = "turn/start"
"""turn 开始事件的 type 字符串。"""

TURN_END_TYPE: str = "turn/end"
"""turn 结束事件的 type 字符串。"""


@dataclass(frozen=True, slots=True)
class StepEntry:
    """单个 step 的折叠结果。

    - ``step`` —— step 序号(在 turn 内从 0 递增)
    - ``started`` —— 是否见过 ``step/start``
    - ``ended`` —— 是否见过 ``step/end``
    """

    step: int
    started: bool = False
    ended: bool = False


@dataclass(frozen=True, slots=True)
class TurnEntry:
    """单个 turn 的折叠结果。

    - ``turn`` —— turn 序号
    - ``started`` —— 是否见过 ``turn/start``
    - ``ended`` —— 是否见过 ``turn/end``
    - ``steps`` —— 该 turn 下已见过的 step(按 step 序号排序)
    """

    turn: int
    started: bool = False
    ended: bool = False
    steps: tuple[StepEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class StepTree:
    """事件流折叠出的 turn/step 树(对齐 DSH SessionEventMap turn/step 语义)。

    - ``turns`` —— 按 turn 序号排序的 turn 条目序列
    - ``active_turn`` —— 最近 ``turn/start`` 且未 ``turn/end`` 的 turn 序号;
      无活跃 turn 时为 None
    - ``active_step`` —— 最近 ``step/start`` 且未 ``step/end`` 的 (turn, step)
      对;无活跃 step 时为 None

    frozen + slots 保证 fold 结果不被原地改;每次 fold 返回新实例。
    """

    turns: tuple[TurnEntry, ...] = ()
    active_turn: int | None = None
    active_step: tuple[int, int] | None = None


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


def fold_step_tree(
    events: Iterable[Any],
    *,
    from_: StepTree | None = None,
) -> StepTree:
    """离线 fold — 扫一遍事件流,重建 turn/step 树(对齐 DSH 事件语义)。

    识别的事件类型:

    - ``turn/start`` → 开新 turn
    - ``turn/end`` → 关闭最近 turn
    - ``step/start`` → 在活跃 turn 内开新 step
    - ``step/end`` → 关闭活跃 turn 内最近 step

    非上述类型一律跳过;``from_`` 续接上次 fold 结果(增量 fold)。
    返回新 ``StepTree`` 实例;不修改入参。

    与 DSH 差异(显式列出):

    - DSH 的 turn/step 事件是 Session.append 的 typed event;
      LCA 的 fold_step_tree 从任意事件流(内存 log / spine dict / SessionEvent)
      重建,不限定具体容器
    - DSH 不在 fold 模块暴露 step tree(由 Session 内部维护);
      LCA 显式提取为纯函数,供 viewer / explain / debug-run 离线重建
    """
    turns_map: dict[int, dict[str, Any]] = {}
    steps_map: dict[int, dict[int, dict[str, Any]]] = {}
    active_turn: int | None = None
    active_step: tuple[int, int] | None = None

    if from_ is not None:
        for te in from_.turns:
            turn_d: dict[str, Any] = {"started": te.started, "ended": te.ended}
            turns_map[te.turn] = turn_d
            step_d: dict[int, dict[str, Any]] = {}
            for se in te.steps:
                step_d[se.step] = {"started": se.started, "ended": se.ended}
            steps_map[te.turn] = step_d
        active_turn = from_.active_turn
        active_step = from_.active_step

    for event in events:
        coerced = _coerce_step_tree_event(event)
        if coerced is None:
            continue
        event_type, data = coerced

        if event_type == TURN_START_TYPE:
            turn_num = data.get("turn")
            if isinstance(turn_num, int):
                turns_map.setdefault(turn_num, {"started": False, "ended": False})
                turns_map[turn_num]["started"] = True
                active_turn = turn_num
                active_step = None

        elif event_type == TURN_END_TYPE:
            turn_num = data.get("turn")
            if isinstance(turn_num, int) and turn_num in turns_map:
                turns_map[turn_num]["ended"] = True
                if active_turn == turn_num:
                    active_turn = None
                    active_step = None

        elif event_type == STEP_START_TYPE:
            turn_num = data.get("turn")
            step_num = data.get("step")
            if isinstance(turn_num, int) and isinstance(step_num, int):
                steps_map.setdefault(turn_num, {})
                steps_map[turn_num].setdefault(step_num, {"started": False, "ended": False})
                steps_map[turn_num][step_num]["started"] = True
                active_step = (turn_num, step_num)

        elif event_type == STEP_END_TYPE:
            turn_num = data.get("turn")
            step_num = data.get("step")
            if (
                isinstance(turn_num, int)
                and isinstance(step_num, int)
                and turn_num in steps_map
                and step_num in steps_map[turn_num]
            ):
                steps_map[turn_num][step_num]["ended"] = True
                if active_step == (turn_num, step_num):
                    active_step = None

    turn_entries: list[TurnEntry] = []
    for turn_num in sorted(turns_map):
        td = turns_map[turn_num]
        sd = steps_map.get(turn_num, {})
        step_entries = tuple(
            StepEntry(step=s, started=sd[s]["started"], ended=sd[s]["ended"]) for s in sorted(sd)
        )
        turn_entries.append(
            TurnEntry(turn=turn_num, started=td["started"], ended=td["ended"], steps=step_entries)
        )

    return StepTree(
        turns=tuple(turn_entries),
        active_turn=active_turn,
        active_step=active_step,
    )


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
class SurfaceFoldReplacement:
    """fold 过程中观察到的一次 replace。

    - ``seq`` — 替换节点自身的 log seq
    - ``start`` / ``end`` — 声明的被替换区间(含端点)
    - ``shadowed_seqs`` — 实际从 surface 摘掉的节点,surface 顺序
    """

    seq: int
    start: int
    end: int
    shadowed_seqs: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SurfaceFoldResult:
    """``foldSurface`` 的完整结果。

    - ``nodes`` — 当前模型可见 surface 的 seq,顺序即模型可见顺序
    - ``replacements`` — 按事件顺序记录的 replace;空 tuple 表示从未替换
    """

    nodes: tuple[int, ...]
    replacements: tuple[SurfaceFoldReplacement, ...] = ()


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
        has_surface_op=surface_op is not _MISSING,
        has_source_event_seqs=sources is not _MISSING,
    )


def _is_event_seq(value: object) -> bool:
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
        raise ValueError(
            f'session event "{view.type}" is surface-eligible and requires a surfaceOp marker'
        )
    op = view.surface_op
    if op == "append":
        return "append"
    if op is None or not isinstance(op, (Mapping, SurfaceReplaceOp)):
        raise ValueError(f'session event "{view.type}" carries an invalid surfaceOp')
    parsed = _as_replace_op(op)
    if parsed is None:
        raise ValueError(f'session event "{view.type}" carries an invalid replace surfaceOp')
    return parsed


def _assert_provenance(view: _EventView, shadowed_seqs: tuple[int, ...]) -> None:
    """校验 ``sourceEventSeqs``:形态、早于本 seq、覆盖全部被 shadow 的节点。"""
    sources: set[int] = set()
    if view.has_source_event_seqs:
        raw = view.source_event_seqs
        if not isinstance(raw, (list, tuple)):
            raise ValueError(
                f"sourceEventSeqs on event at seq {view.seq} must be an array when present"
            )
        if len(raw) == 0 and view.type != SURFACE_ASSISTANT_TYPE:
            raise ValueError(
                f"sourceEventSeqs must not be empty except on {SURFACE_ASSISTANT_TYPE}"
            )
        non_earlier: object = None
        for source in raw:
            if not _is_event_seq(source):
                raise ValueError(
                    f'session event "{view.type}" sourceEventSeqs must densely '
                    "contain non-negative safe integers"
                )
            sources.add(source)
            if non_earlier is None and isinstance(view.seq, int) and source >= view.seq:
                non_earlier = source
        if len(sources) != len(raw):
            raise ValueError("sourceEventSeqs must not contain duplicates")
        if non_earlier is not None:
            raise ValueError(
                f"sourceEventSeqs must reference earlier events: "
                f"{non_earlier} >= current seq {view.seq}"
            )
    missing = [seq for seq in shadowed_seqs if seq not in sources]
    if missing:
        joined = ", ".join(str(seq) for seq in missing)
        raise ValueError(
            "surface replace: sourceEventSeqs must include every shadowed "
            f"surface node; missing {joined}"
        )


def _replacement_range(nodes: list[int], op: SurfaceReplaceOp) -> tuple[int, int, tuple[int, ...]]:
    """定位 replace 区间;不改 ``nodes``。返回 ``(start_idx, end_idx, shadowed)``。"""
    try:
        start_idx = nodes.index(op.start)
    except ValueError:
        raise ValueError(f"surface replace: start seq {op.start} not found in surface") from None
    try:
        end_idx = nodes.index(op.end)
    except ValueError:
        raise ValueError(f"surface replace: end seq {op.end} not found in surface") from None
    if start_idx > end_idx:
        raise ValueError(
            f"surface replace: start seq {op.start} (index {start_idx}) "
            f"is after end seq {op.end} (index {end_idx})"
        )
    return start_idx, end_idx, tuple(nodes[start_idx : end_idx + 1])


def _json_equal(a: object, b: object) -> bool:
    """JSON 值域结构相等(键排序);非 JSON 值走 ``default=str``。"""
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _tool_result_rest(data: Mapping[str, Any]) -> object:
    """去掉可变 content 后的 tool-result payload,供 rewrite 比对。

    dsh 形态(``data.message.content[0]``):只允许改 ``content[0].content``。
    LCA 形态:只允许改顶层 ``outcome`` / ``content`` / ``result``。
    """
    message = data.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, (list, tuple)) and content:
            first = content[0]
            nulled_first: object = (
                {**first, "content": None} if isinstance(first, Mapping) else first
            )
            nulled_message = {**message, "content": [nulled_first, *list(content[1:])]}
            return {**data, "message": nulled_message}
    return {k: v for k, v in data.items() if k not in {"outcome", "content", "result"}}


def _assert_tool_result_rewrite(
    view: _EventView,
    shadowed_seqs: tuple[int, ...],
    log: tuple[_EventView, ...],
) -> None:
    """tool-result replace:必须覆盖恰好一个当前 tool-result 节点,且只改 content。"""
    if view.type != SURFACE_TOOL_RESULT_TYPE:
        return
    if len(shadowed_seqs) != 1:
        raise ValueError(
            f"{SURFACE_TOOL_RESULT_TYPE} surface replacement must rewrite exactly one current node"
        )
    original_seq = shadowed_seqs[0]
    if (
        original_seq < 0
        or original_seq >= len(log)
        or log[original_seq].type != SURFACE_TOOL_RESULT_TYPE
    ):
        raise ValueError(
            f"{SURFACE_TOOL_RESULT_TYPE} surface replacement must target a current "
            f"{SURFACE_TOOL_RESULT_TYPE}"
        )
    if not _json_equal(_tool_result_rest(log[original_seq].data), _tool_result_rest(view.data)):
        raise ValueError(f"{SURFACE_TOOL_RESULT_TYPE} surface replacement may change only content")


def foldSurface(events: Iterable[Any]) -> SurfaceFoldResult:  # noqa: N802 (dsh parity)
    """离线 fold — 扫一遍事件流,重建当前模型可见 surface(对齐 dsh ``foldSurface``)。

    输入是从 seq 0 起连续的完整 log(或 log 前缀)。每条事件占用一个 seq 槽;
    非 surface 事件不进 ``nodes``,但仍参与连续性校验。

    词表映射见 :data:`SURFACE_EVENT_TYPES`。信封同时接受 SessionEvent
    (``type`` / ``data``)与 spine 形态(``category`` / ``payload``);
    ``surfaceOp`` / ``surface_op``、``sourceEventSeqs`` / ``source_event_seqs``
    等价。

    失败语义(``ValueError``):seq 不连续、合格类型缺 marker、非合格类型
    带 marker、replace 区间不在当前 surface、provenance 不覆盖被
    shadow 节点、tool-result replace 改了 content 以外的字段。

    所有权:返回新 tuple,不修改入参。无 I/O。不导出 SurfaceManager
    (增量 live view 由 Session 运行时持有,不在本纯函数模块)。
    """
    log = tuple(_parse_event(event) for event in events)
    nodes: list[int] = []
    replacements: list[SurfaceFoldReplacement] = []

    for index, view in enumerate(log):
        if view.seq != index:
            raise ValueError(f"session event seq {view.seq} is not contiguous; expected {index}")
        surface_op = _surface_op_of(view)
        if surface_op is None:
            continue
        if not _is_event_seq(view.seq):
            raise ValueError(f"session event seq {view.seq} is not contiguous; expected {index}")
        seq = int(view.seq)
        if surface_op == "append":
            _assert_provenance(view, ())
            nodes.append(seq)
            continue
        start_idx, end_idx, shadowed = _replacement_range(nodes, surface_op)
        _assert_provenance(view, shadowed)
        _assert_tool_result_rewrite(view, shadowed, log)
        nodes[start_idx : end_idx + 1] = [seq]
        replacements.append(
            SurfaceFoldReplacement(
                seq=seq,
                start=surface_op.start,
                end=surface_op.end,
                shadowed_seqs=shadowed,
            )
        )

    return SurfaceFoldResult(nodes=tuple(nodes), replacements=tuple(replacements))


__all__ = [
    "REQUEST_HEADER_CATEGORY",
    "STEP_END_TYPE",
    "STEP_START_TYPE",
    "SURFACE_ASSISTANT_TYPE",
    "SURFACE_EVENT_TYPES",
    "SURFACE_TOOL_RESULT_TYPE",
    "SURFACE_USER_TYPE",
    "TURN_END_TYPE",
    "TURN_START_TYPE",
    "EpochHeader",
    "StepEntry",
    "StepTree",
    "SurfaceFoldReplacement",
    "SurfaceFoldResult",
    "SurfaceReplaceOp",
    "TurnEntry",
    "canonicalHeader",
    "foldRequestHeader",
    "foldSurface",
    "fold_step_tree",
    "headerEquals",
    "isAppendSurfaceEvent",
    "isReplacementSurfaceEvent",
    "isSurfaceEligibleType",
    "isSurfaceEvent",
]
