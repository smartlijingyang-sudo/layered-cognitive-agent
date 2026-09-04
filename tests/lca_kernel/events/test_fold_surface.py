"""foldSurface 契约 —— ADR-0186 I-SESSION-2,对齐 dsh surface.ts 语义。

词表是 LCA spine / model-visible,不是 dsh ``user/message`` 三件套。
映射锁在 :data:`SURFACE_EVENT_TYPES` 与 ``test_dsh_type_names_are_not_eligible``。
"""

from __future__ import annotations

from typing import Any

import pytest

from lca_kernel.events.fold import (
    SURFACE_ASSISTANT_TYPE,
    SURFACE_EVENT_TYPES,
    SURFACE_TOOL_RESULT_TYPE,
    SURFACE_USER_TYPE,
    SurfaceFoldReplacement,
    SurfaceFoldResult,
    SurfaceReplaceOp,
    foldSurface,
    isAppendSurfaceEvent,
    isReplacementSurfaceEvent,
    isSurfaceEligibleType,
    isSurfaceEvent,
)

USER = SURFACE_USER_TYPE
ASSISTANT = SURFACE_ASSISTANT_TYPE
TOOL = SURFACE_TOOL_RESULT_TYPE


def ev(
    seq: int,
    type_: str,
    *,
    surface_op: object = "append",
    sources: object | None = None,
    data: dict[str, Any] | None = None,
    marker: bool = True,
    snake: bool = False,
) -> dict[str, Any]:
    """最小 surface 信封。``marker=False`` 省略 surfaceOp;``snake=True`` 走 snake_case 键。"""
    event: dict[str, Any] = {"type": type_, "seq": seq, "data": data or {}}
    op_key = "surface_op" if snake else "surfaceOp"
    src_key = "source_event_seqs" if snake else "sourceEventSeqs"
    if marker:
        event[op_key] = surface_op
    if sources is not None:
        event[src_key] = sources
    return event


def tool_data(
    *,
    tool_name: str = "bash",
    invocation_id: str = "inv-1",
    attempt: int = 1,
    outcome: str = "success",
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "invocation_id": invocation_id,
        "attempt": attempt,
        "outcome": outcome,
    }


def dsh_tool_data(call_id: str, content: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "turn": 1,
        "step": 1,
        "message": {
            "role": "tool",
            "content": [
                {
                    "type": "text",
                    "content": content,
                    "toolCallId": call_id,
                    "isError": is_error,
                }
            ],
        },
    }


# ── 词表映射 ─────────────────────────────────────────────────────────────


def test_dsh_type_names_are_not_eligible() -> None:
    """dsh 原名不是 LCA surface 闭集;必须先映射到 spine category。"""
    assert isSurfaceEligibleType("user/message") is False
    assert isSurfaceEligibleType("assistant/message") is False
    assert isSurfaceEligibleType("tool/result") is False
    assert isSurfaceEligibleType(USER) is True
    assert isSurfaceEligibleType(ASSISTANT) is True
    assert isSurfaceEligibleType(TOOL) is True
    assert isSurfaceEligibleType("turn/start") is False
    assert isSurfaceEligibleType("spine.llm.call.start") is False
    assert frozenset({USER, ASSISTANT, TOOL}) == SURFACE_EVENT_TYPES


# ── 空流 / 非 surface ────────────────────────────────────────────────────


def test_empty_log_yields_empty_surface() -> None:
    assert foldSurface([]) == SurfaceFoldResult(nodes=(), replacements=())


def test_non_surface_events_do_not_join_nodes() -> None:
    events = [
        {"type": "turn/start", "seq": 0, "data": {"turn": 1}},
        {"type": "spine.llm.call.start", "seq": 1, "data": {"model": "m"}},
        {"type": "turn/end", "seq": 2, "data": {"turn": 1}},
    ]
    assert foldSurface(events).nodes == ()


# ── append ───────────────────────────────────────────────────────────────


def test_append_markers_build_ordered_nodes() -> None:
    events = [
        {"type": "turn/start", "seq": 0, "data": {"turn": 1}},
        ev(1, USER),
        ev(2, ASSISTANT),
        {"type": "turn/end", "seq": 3, "data": {"turn": 1}},
        ev(4, TOOL, data=tool_data()),
    ]
    result = foldSurface(events)
    assert result.nodes == (1, 2, 4)
    assert result.replacements == ()


def test_snake_case_and_category_payload_aliases() -> None:
    events = [
        {
            "category": USER,
            "seq": 0,
            "payload": {"messages": []},
            "surface_op": "append",
        },
        ev(1, ASSISTANT, snake=True),
    ]
    assert foldSurface(events).nodes == (0, 1)


# ── replace ──────────────────────────────────────────────────────────────


def test_replace_splices_shadowed_range() -> None:
    events = [
        ev(0, USER),
        ev(1, ASSISTANT),
        ev(
            2,
            ASSISTANT,
            surface_op={"op": "replace", "start": 0, "end": 1},
            sources=[0, 1],
        ),
    ]
    result = foldSurface(events)
    assert result.nodes == (2,)
    assert result.replacements == (
        SurfaceFoldReplacement(seq=2, start=0, end=1, shadowed_seqs=(0, 1)),
    )


def test_replace_range_preserves_nodes_outside() -> None:
    events = [
        ev(0, USER, data={"text": "a"}),
        ev(1, USER, data={"text": "b"}),
        ev(2, USER, data={"text": "c"}),
        ev(
            3,
            ASSISTANT,
            surface_op={"op": "replace", "start": 0, "end": 1},
            sources=[0, 1],
        ),
    ]
    assert foldSurface(events).nodes == (3, 2)


def test_single_node_replace() -> None:
    events = [
        ev(0, USER),
        ev(1, USER),
        ev(
            2,
            ASSISTANT,
            surface_op={"op": "replace", "start": 1, "end": 1},
            sources=[1],
        ),
    ]
    assert foldSurface(events).nodes == (0, 2)


def test_mid_replace_preserves_surrounding_order() -> None:
    events = [
        ev(0, USER),
        ev(1, USER),
        ev(2, USER),
        ev(
            3,
            ASSISTANT,
            surface_op={"op": "replace", "start": 1, "end": 1},
            sources=[1],
        ),
    ]
    assert foldSurface(events).nodes == (0, 3, 2)


def test_replace_op_dataclass_is_accepted() -> None:
    events = [
        ev(0, USER),
        ev(
            1,
            ASSISTANT,
            surface_op=SurfaceReplaceOp(op="replace", start=0, end=0),
            sources=[0],
        ),
    ]
    assert foldSurface(events).nodes == (1,)


# ── 校验失败 ─────────────────────────────────────────────────────────────


def test_eligible_event_requires_surface_op_marker() -> None:
    with pytest.raises(ValueError, match="requires a surfaceOp marker"):
        foldSurface([{"type": USER, "seq": 0, "data": {}}])


def test_non_eligible_cannot_carry_surface_op() -> None:
    with pytest.raises(ValueError, match="cannot carry surfaceOp"):
        foldSurface([{"type": "turn/start", "seq": 0, "data": {"turn": 1}, "surfaceOp": "append"}])


def test_non_eligible_cannot_carry_source_event_seqs() -> None:
    with pytest.raises(ValueError, match="cannot carry sourceEventSeqs"):
        foldSurface([{"type": "turn/start", "seq": 0, "data": {"turn": 1}, "sourceEventSeqs": [0]}])


def test_seq_must_be_contiguous_from_zero() -> None:
    with pytest.raises(ValueError, match="is not contiguous; expected 1"):
        foldSurface([ev(0, USER), ev(2, ASSISTANT)])


@pytest.mark.parametrize(
    ("op", "match"),
    [
        ("nope", "invalid surfaceOp"),
        (None, "invalid surfaceOp"),
        ({"op": "replace", "start": 0}, "invalid replace surfaceOp"),
        ({"op": "replace", "start": 0, "end": 0, "extra": 1}, "invalid replace surfaceOp"),
        ({"op": "replace", "start": -1, "end": 0}, "invalid replace surfaceOp"),
        ({"op": "append", "start": 0, "end": 0}, "invalid replace surfaceOp"),
    ],
)
def test_invalid_surface_op_shapes(op: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        foldSurface([ev(0, USER, surface_op=op)])


def test_replace_start_not_on_surface() -> None:
    events = [
        ev(0, USER),
        ev(
            1,
            ASSISTANT,
            surface_op={"op": "replace", "start": 5, "end": 0},
            sources=[0],
        ),
    ]
    with pytest.raises(ValueError, match="start seq 5 not found"):
        foldSurface(events)


def test_replace_end_not_on_surface() -> None:
    events = [
        ev(0, USER),
        ev(
            1,
            ASSISTANT,
            surface_op={"op": "replace", "start": 0, "end": 99},
            sources=[0],
        ),
    ]
    with pytest.raises(ValueError, match="end seq 99 not found"):
        foldSurface(events)


def test_replace_start_after_end() -> None:
    events = [
        ev(0, USER),
        ev(1, USER),
        ev(
            2,
            ASSISTANT,
            surface_op={"op": "replace", "start": 1, "end": 0},
            sources=[1, 0],
        ),
    ]
    with pytest.raises(ValueError, match="after end seq 0"):
        foldSurface(events)


# ── provenance ───────────────────────────────────────────────────────────


def test_replace_accepts_complete_source_coverage() -> None:
    events = [
        ev(0, USER),
        ev(1, USER),
        ev(
            2,
            USER,
            surface_op={"op": "replace", "start": 0, "end": 1},
            sources=[0, 1],
        ),
    ]
    assert foldSurface(events).nodes == (2,)


def test_assistant_may_carry_empty_source_list_on_append() -> None:
    assert foldSurface([ev(0, ASSISTANT, sources=[])]).nodes == (0,)


def test_user_empty_source_list_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        foldSurface([ev(0, USER, sources=[])])


@pytest.mark.parametrize(
    ("events", "match"),
    [
        ([ev(0, USER, sources="invalid")], "must be an array"),
        ([ev(0, USER), ev(1, USER, sources=[0, 0])], "must not contain duplicates"),
        ([ev(0, USER, sources=[0.5])], "non-negative safe integers"),
        ([ev(0, USER, sources=[-1])], "non-negative safe integers"),
        ([ev(0, USER, sources=["0"])], "non-negative safe integers"),
        ([ev(0, USER, sources=[0])], "must reference earlier events"),
        (
            [
                ev(0, USER),
                ev(1, USER),
                ev(
                    2,
                    USER,
                    surface_op={"op": "replace", "start": 0, "end": 1},
                    sources=[0],
                ),
            ],
            "missing 1",
        ),
    ],
)
def test_provenance_rejects_malformed_sources(events: list[dict[str, Any]], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        foldSurface(events)


# ── tool-result rewrite ──────────────────────────────────────────────────


def test_tool_result_replace_must_cover_exactly_one_node() -> None:
    events = [
        ev(0, USER),
        ev(1, USER),
        ev(
            2,
            TOOL,
            surface_op={"op": "replace", "start": 0, "end": 1},
            sources=[0, 1],
            data=tool_data(),
        ),
    ]
    with pytest.raises(ValueError, match="exactly one current node"):
        foldSurface(events)


def test_tool_result_replace_must_target_tool_result() -> None:
    events = [
        ev(0, USER),
        ev(
            1,
            TOOL,
            surface_op={"op": "replace", "start": 0, "end": 0},
            sources=[0],
            data=tool_data(),
        ),
    ]
    with pytest.raises(ValueError, match="must target a current"):
        foldSurface(events)


def test_tool_result_replace_may_change_only_outcome() -> None:
    original = ev(0, TOOL, data=tool_data(outcome="running"))
    ok = ev(
        1,
        TOOL,
        surface_op={"op": "replace", "start": 0, "end": 0},
        sources=[0],
        data=tool_data(outcome="success"),
    )
    assert foldSurface([original, ok]).nodes == (1,)

    drifted = ev(
        1,
        TOOL,
        surface_op={"op": "replace", "start": 0, "end": 0},
        sources=[0],
        data=tool_data(outcome="success", invocation_id="inv-other"),
    )
    with pytest.raises(ValueError, match="may change only content"):
        foldSurface([original, drifted])


def test_tool_result_dsh_message_shape_allows_content_only() -> None:
    original = ev(0, TOOL, data=dsh_tool_data("c1", "old"))
    ok = ev(
        1,
        TOOL,
        surface_op={"op": "replace", "start": 0, "end": 0},
        sources=[0],
        data=dsh_tool_data("c1", "new"),
    )
    assert foldSurface([original, ok]).nodes == (1,)

    changed_id = ev(
        1,
        TOOL,
        surface_op={"op": "replace", "start": 0, "end": 0},
        sources=[0],
        data=dsh_tool_data("c2", "old"),
    )
    with pytest.raises(ValueError, match="may change only content"):
        foldSurface([original, changed_id])


# ── type guards ──────────────────────────────────────────────────────────


def test_surface_event_guards() -> None:
    appended = ev(0, USER)
    replacement = ev(
        1,
        ASSISTANT,
        surface_op={"op": "replace", "start": 0, "end": 0},
        sources=[0],
    )
    markerless = {"type": USER, "seq": 0, "data": {}}
    boundary = {"type": "turn/start", "seq": 0, "data": {"turn": 1}}

    assert isSurfaceEvent(appended) is True
    assert isAppendSurfaceEvent(appended) is True
    assert isReplacementSurfaceEvent(appended) is False

    assert isSurfaceEvent(replacement) is True
    assert isAppendSurfaceEvent(replacement) is False
    assert isReplacementSurfaceEvent(replacement) is True

    assert isSurfaceEvent(markerless) is False
    assert isAppendSurfaceEvent(markerless) is False
    assert isReplacementSurfaceEvent(markerless) is False
    assert isSurfaceEvent(boundary) is False
    assert isAppendSurfaceEvent(boundary) is False
    assert isReplacementSurfaceEvent(boundary) is False
