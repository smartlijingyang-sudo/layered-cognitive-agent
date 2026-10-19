"""RA-169: the unmounted-widget seam admits a third widget kind.

Pins the parameterized seam (_WidgetKind / _WidgetField /
_extract_unmounted_widgets / _ensure_widgets_in_assistant_message) with a
hypothetical third widget kind ("widget:receipt") — proving the seam is a
real seam, not just two copies DRY-ed together.
"""

from __future__ import annotations

import re

from lca.runtime.session.run_session_writer import (
    _ensure_widgets_in_assistant_message,
    _extract_unmounted_widgets,
    _WidgetField,
    _WidgetKind,
)


def _receipt_kind() -> _WidgetKind:
    return _WidgetKind(
        name="receipt",
        tag_re=re.compile(r"\[widget:receipt\?([^\]]+)\]"),
        id_field="receipt_id",
        fields=(
            _WidgetField("receiptId", "receipt_id", ("receipt_id",), "", False, ("receipt_id",)),
            _WidgetField("total", "total", (), "0", False, ("total",)),
            _WidgetField("note", "note", (), "", True, ("note",)),
        ),
        fallback_source="meta_or_data",
        fallback_required=("receipt_id", "total"),
    )


class _Ev:
    def __init__(self, event_type: str, data: dict) -> None:
        self.type = event_type
        self.data = data


_TOOL_RESULT = "spine.body.tool.execute.end"
_ASSISTANT = "spine.llm.request.header.assistant"


def test_third_kind_extracts_unmounted_from_tag() -> None:
    kind = _receipt_kind()
    events = [
        _Ev(
            _TOOL_RESULT,
            {"content": "done [widget:receipt?receiptId=r-1&total=42]"},
        )
    ]
    pending = _extract_unmounted_widgets(events, kind)
    assert pending == [{"receipt_id": "r-1", "total": "42", "note": ""}]


def test_third_kind_extracts_from_meta_fallback() -> None:
    kind = _receipt_kind()
    events = [
        _Ev(_TOOL_RESULT, {"content": "no tag here", "meta": {"receipt_id": "r-2", "total": "7"}})
    ]
    pending = _extract_unmounted_widgets(events, kind)
    assert pending == [{"receipt_id": "r-2", "total": "7", "note": ""}]


def test_third_kind_skips_mounted_and_dedupes() -> None:
    kind = _receipt_kind()
    events = [
        _Ev(_TOOL_RESULT, {"content": "[widget:receipt?receiptId=r-1&total=1]"}),
        _Ev(_TOOL_RESULT, {"content": "[widget:receipt?receiptId=r-1&total=1]"}),
        _Ev(_ASSISTANT, {"content": "see [widget:receipt?receiptId=r-1&total=1]"}),
    ]
    assert _extract_unmounted_widgets(events, kind) == []


def test_third_kind_ensure_appends_and_dedupes() -> None:
    kind = _receipt_kind()
    pending = [{"receipt_id": "r-9", "total": "100", "note": "vip"}]
    out = _ensure_widgets_in_assistant_message("thanks", pending, kind)
    assert "[widget:receipt?receiptId=r-9&total=100&note=vip]" in out
    # note omitted when empty (omit_if_empty)
    out2 = _ensure_widgets_in_assistant_message("thanks", [{"receipt_id": "r-9", "total": "100", "note": ""}], kind)
    assert "note=" not in out2
    # already present -> not duplicated
    assert _ensure_widgets_in_assistant_message(out, pending, kind) == out
