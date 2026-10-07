"""Wave 1: known-types fail-closed + ignorable skip（验收 #6 / #12）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lca.plugins.session.runtime.log.reader import SessionLogReadError, load_session_events
from lca.session.catalog import (
    UnknownSessionEventTypeError,
    known_session_event_types,
    validate_event_type_for_read,
)


def test_known_types_includes_registered_session_events() -> None:
    assert "turn.started.v1" in known_session_event_types()
    assert "feedback.record.v1" in known_session_event_types()
    assert "session.end_seed.v1" in known_session_event_types()


def test_unknown_non_ignorable_rejected() -> None:
    with pytest.raises(UnknownSessionEventTypeError):
        validate_event_type_for_read("totally/unknown", ignorable=False)


def test_ignorable_unknown_allowed() -> None:
    validate_event_type_for_read("totally/unknown", ignorable=True)


def test_spine_execution_points_are_known() -> None:
    validate_event_type_for_read("body.tool.execute.start")
    validate_event_type_for_read("spine.body.tool.execute.end")


def test_dirty_log_rejected_on_open(tmp_path: Path) -> None:
    path = tmp_path / "run_1.spine.jsonl"
    path.write_text(
        json.dumps({"type": "mystery/event", "seq": 0, "time": 1, "data": {}}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SessionLogReadError):
        load_session_events(path, session_id="run_1")


def test_ignorable_unknown_skipped_on_open(tmp_path: Path) -> None:
    path = tmp_path / "run_2.spine.jsonl"
    lines = [
        json.dumps({"type": "turn.started.v1", "seq": 0, "time": 1, "data": {"turn": 1}}),
        json.dumps(
            {
                "type": "plugin/only",
                "seq": 1,
                "time": 2,
                "data": {},
                "ignorable": True,
            }
        ),
        json.dumps(
            {"type": "turn.ended.v1", "seq": 2, "time": 3, "data": {"turn": 1, "reason": "x"}}
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    events = load_session_events(path, session_id="run_2")
    assert len(events) == 3
    assert events[1].ignorable is True
    assert events[1].type == "plugin/only"


def test_known_types_is_pure_registered_vocabulary_union() -> None:
    """known_session_event_types() 是纯具名词表的并集：catalog 内零手工字面量。"""
    from lca.contracts.harness.tasks.session import event_registry
    from lca.session.surface_types import DSH_SURFACE_EVENT_TYPES
    from lca_kernel.events.fold.fold import SURFACE_EVENT_TYPES
    from lca_kernel.events.payloads.spine import (
        SPINE_EVENT_CATEGORIES,
        SPINE_EXECUTION_POINTS,
    )

    expected = (
        set(event_registry())
        | set(SURFACE_EVENT_TYPES)
        | set(SPINE_EXECUTION_POINTS)
        | set(SPINE_EVENT_CATEGORIES)
        | set(DSH_SURFACE_EVENT_TYPES)
    )
    assert known_session_event_types() == frozenset(expected)
    assert "surface/developer_message" in known_session_event_types()


def test_dsh_surface_vocabulary_is_single_sourced() -> None:
    """DSH surface 词表 single source：writer 与 catalog 共用同一常量。"""
    from lca.runtime.session import run_session_writer
    from lca.session import surface_types

    assert surface_types.DEVELOPER_MESSAGE_TYPE == "surface/developer_message"
    assert frozenset({"surface/developer_message"}) == surface_types.DSH_SURFACE_EVENT_TYPES
    assert run_session_writer.DEVELOPER_MESSAGE_TYPE is surface_types.DEVELOPER_MESSAGE_TYPE
