"""SpineClock 生产路径委托共享 UTC seam 的回归测试。

历史上 ``SpineClock.now_iso()`` 直接 ``datetime.now(UTC).isoformat()``（微秒 +
``+00:00``），与 ``lca.contracts.atoms.ids.ids.utc_now_iso``（``%Y-%m-%dT%H:%M:%SZ``）
格式漂移。本轮改为：真实时间走共享 seam，``freeze()`` 保留测试注入能力。
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

from lca_kernel.events.spine.runtime import SpineClock

_ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_now_iso_is_utc_iso_8601_string() -> None:
    """未 freeze 时 ``now_iso()`` 必须是 seam 的 ``%Y-%m-%dT%H:%M:%SZ``。"""
    SpineClock.freeze(None)
    iso = SpineClock.now_iso()
    assert _ISO_UTC_RE.match(iso), f"now_iso() 应为 %Y-%m-%dT%H:%M:%SZ，得到 {iso!r}"
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_now_ms_is_utc_epoch_millis() -> None:
    """未 freeze 时 ``now_ms()`` 委托 ``utc_now_ms``。"""
    SpineClock.freeze(None)
    before = int(time.time() * 1000)
    value = SpineClock.now_ms()
    after = int(time.time() * 1000)
    assert before <= value <= after


def test_now_returns_utc_aware_datetime() -> None:
    SpineClock.freeze(None)
    now = SpineClock.now()
    assert now.tzinfo is not None
    assert now.utcoffset() is not None
    assert now.utcoffset().total_seconds() == 0


def test_freeze_respected_by_all_production_methods() -> None:
    """``freeze()`` 仍固定所有时间出口；解除后恢复墙钟。"""
    fixed = datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC)
    SpineClock.freeze(fixed)
    try:
        assert SpineClock.now() == fixed
        assert SpineClock.now_iso() == "2026-09-03T12:00:00+00:00"
        assert SpineClock.now_ms() == int(fixed.timestamp() * 1000)
    finally:
        SpineClock.freeze(None)


def test_unfreeze_restores_wall_clock() -> None:
    SpineClock.freeze(datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC))
    SpineClock.freeze(None)
    assert SpineClock.now_iso().endswith("Z")
    assert SpineClock.now().tzinfo is not None
