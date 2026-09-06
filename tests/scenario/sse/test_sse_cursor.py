from __future__ import annotations

import pytest

from lca.contracts.harness.perceive.sse_cursor import SseCursor


def test_sse_cursor_advances_monotonically() -> None:
    cursor = SseCursor("session-1")
    cursor = cursor.advance(3)
    assert cursor.last_seq == 3
    assert cursor.next_seq() == 4
    assert cursor.advance(2).last_seq == 3


def test_sse_cursor_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        SseCursor("", -1)
    with pytest.raises(ValueError):
        SseCursor("session-1", -2)
