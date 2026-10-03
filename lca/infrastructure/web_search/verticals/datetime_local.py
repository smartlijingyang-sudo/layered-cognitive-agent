"""Datetime vertical：本地时间，纯 stdlib，无网络.

返回 ISO 时间 + 日期 + 星期 + 时区名 + UTC 偏移 —— vertical 的五个维度
在这里是 trivially 满足的（数据源就是本机时钟）.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


@dataclass(frozen=True, slots=True)
class LocalTime:
    """当前本地时间."""

    iso: str  # 完整 ISO，如 2026-10-03T08:05:00+08:00
    date: str  # 如 2026-10-03
    time: str  # 如 08:05:00
    weekday: str  # 周一..周日
    tz_name: str  # 如 Asia/Shanghai
    utc_offset: str  # 如 +08:00


def now(tz: str | None = None) -> LocalTime:
    """返回当前本地时间. ``tz`` 为 IANA 时区名，缺省用本机时区."""
    dt = datetime.now(ZoneInfo(tz) if tz else None).astimezone()
    tzinfo = dt.tzinfo
    tz_name = tz or (tzinfo.key if hasattr(tzinfo, "key") else str(tzinfo))
    offset = dt.strftime("%z")
    utc_offset = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
    return LocalTime(
        iso=dt.isoformat(timespec="seconds"),
        date=dt.strftime("%Y-%m-%d"),
        time=dt.strftime("%H:%M:%S"),
        weekday=_WEEKDAYS[dt.weekday()],
        tz_name=tz_name,
        utc_offset=utc_offset,
    )
