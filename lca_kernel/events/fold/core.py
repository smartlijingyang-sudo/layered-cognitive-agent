"""Fold core —— 扫事件流重建投影的纯函数算法。

依赖 :mod:`lca_kernel.events.fold.inputs` 提供的事件归一视图与
:mod:`lca_kernel.events.fold.projection` 定义的投影结果类型:

- :func:`foldRequestHeader` —— 重建最近生效的 canonical header
- :func:`fold_step_tree` —— 重建 turn/step 树
- :func:`foldSurface` —— 重建当前模型可见 surface

本模块是纯函数集,无 I/O、无副作用。不依赖具体 LLM/Reasoner/Brain/Body/
SafeExecutor;只读事件流形态,任何上游(``<run_id>.spine.jsonl`` 重放、
sub-batch 增量 fold、viewer 离线重建)都走同一路径。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from lca_kernel.events.fold.inputs import (
    REQUEST_HEADER_CATEGORY,
    STEP_END_TYPE,
    STEP_START_TYPE,
    SURFACE_ASSISTANT_TYPE,
    SURFACE_TOOL_RESULT_TYPE,
    TURN_END_TYPE,
    TURN_START_TYPE,
    SurfaceReplaceOp,
    _coerce_event,
    _coerce_step_tree_event,
    _EventView,
    _is_event_seq,
    _parse_event,
    _surface_op_of,
)
from lca_kernel.events.fold.projection import (
    EpochHeader,
    StepEntry,
    StepTree,
    SurfaceFoldReplacement,
    SurfaceFoldResult,
    TurnEntry,
    canonicalHeader,
)


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
        seq = view.seq
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
