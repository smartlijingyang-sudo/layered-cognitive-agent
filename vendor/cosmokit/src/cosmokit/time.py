"""Time constants plus parsing and formatting helpers.

1:1 Python port of ``@deepseek-ai/cosmokit/src/time.ts``.

Notes on translation:

- The TS class ``namespace Time`` is exposed as a Python class with
  ``@staticmethod`` members. Mutable module state (the timezone offset)
  is held on the class.
- ``parseDate`` returns milliseconds since the Unix epoch (an ``int``);
  the TS uses ``Date`` which mixes date and numeric representations.
  Tests can compare against ``int(time.time_ns() / 1_000_000)`` plus or minus
  a tolerance window. The relative-offset branches are supported.
- ``format`` uses ``Math.round`` semantics — Python's built-in ``round``
  uses banker's rounding (round half to even), which produces different
  results for ``.5`` ties. We use ``math.floor(x + 0.5)`` to match JS.
- ``toDigits`` matches ``String#padStart``: pads on the left, never truncates.
"""

from __future__ import annotations

import math
import re
import time as _time
from datetime import UTC
from datetime import datetime as _dt


# JS-style Math.round that rounds half away from -∞ (i.e. JS semantics).
def _round(value: float) -> float:
    return math.floor(value + 0.5)


# ---------------------------------------------------------------------------
# Time class (mirrors the TS `namespace Time`)
# ---------------------------------------------------------------------------


# Time-unit constants match the TS values exactly.
_MILLISECOND = 1
_SECOND = 1000
_MINUTE = _SECOND * 60
_HOUR = _MINUTE * 60
_DAY = _HOUR * 24
_WEEK = _DAY * 7


# JS ``new Date().getTimezoneOffset()`` returns minutes west of UTC, i.e.
# for UTC+8 the result is ``-480``. Python's ``time.timezone`` is "seconds
# west of UTC" with a sign convention that produces the same minute count
# after integer division. We snapshot this at import time so a single
# ``Time.set_timezone_offset`` mutation remains consistent.
_TIMEZONE_OFFSET_INIT = _time.timezone // 60


class Time:
    """Time utilities mirroring the upstream ``@deepseek-ai/cosmokit`` namespace."""

    millisecond: int = _MILLISECOND
    second: int = _SECOND
    minute: int = _MINUTE
    hour: int = _HOUR
    day: int = _DAY
    week: int = _WEEK

    _timezone_offset: int = _TIMEZONE_OFFSET_INIT

    # -- Timezone offset --------------------------------------------------

    @staticmethod
    def set_timezone_offset(offset: int) -> None:
        """Set the global timezone offset (minutes, JS convention)."""
        Time._timezone_offset = offset

    @staticmethod
    def get_timezone_offset() -> int:
        """Return the current timezone offset (minutes, JS convention)."""
        return Time._timezone_offset

    # -- parseTime ---------------------------------------------------------

    @staticmethod
    def parseTime(source: str) -> int:
        """Parse a duration string like ``"1w2d3h4m5s"`` to milliseconds.

        Mirrors the TS implementation: groups are optional; missing groups
        contribute 0 to the total.
        """
        m = _TIME_PATTERN.match(source)
        if not m:
            return 0
        weeks, days, hours, minutes, seconds = m.groups()
        return int(
            (float(weeks) if weeks else 0) * Time.week
            + (float(days) if days else 0) * Time.day
            + (float(hours) if hours else 0) * Time.hour
            + (float(minutes) if minutes else 0) * Time.minute
            + (float(seconds) if seconds else 0) * Time.second
        )

    # -- parseDate ---------------------------------------------------------

    @staticmethod
    def parseDate(date: str) -> int:
        """Parse a date / duration string to ``int`` milliseconds since epoch.

        Behaviour:

        - ``"1w2d3h..."`` style: ``now + parseTime``
        - ``"HH:MM[:SS]"`` style: today + that time (``MM/DD/YYYY`` format)
        - ``"DD-MM-YY[:HH:MM[:SS]]"`` style: current year + DMY + optional time
        - anything else: pass to ``datetime.fromisoformat``
        - ``""`` / falsy: now

        Returns ``int`` (ms since epoch) regardless of branch.

        Note on the HMS branch: the TS uses ``Date#toLocaleDateString()`` which
        is locale-dependent. The Python port pins the format to MM/DD/YYYY to
        keep the round-trip deterministic across locales; users who require
        locale-aware behaviour should call ``datetime.fromisoformat`` directly.
        """
        parsed = Time.parseTime(date)
        if parsed:
            return int(_time.time() * 1000) + parsed
        if _TIME_PATTERN_HMS.match(date):
            today_str = _dt.now(tz=UTC).strftime("%m/%d/%Y")
            text = f"{today_str}-{date}"
            # ``:HH`` (1 colon) or ``:HH:MM`` (2 colons) — JS is lenient on
            # the second segment; pick the matching ``strptime`` format.
            if text.count(":") >= 2:
                fmt = "%m/%d/%Y-%H:%M:%S"
            else:
                fmt = "%m/%d/%Y-%H:%M"
            try:
                return int(_dt.strptime(text, fmt).replace(tzinfo=UTC).timestamp() * 1000)
            except ValueError:
                return int(_time.time() * 1000)
        if _TIME_PATTERN_DMY.match(date):
            year = _dt.now(tz=UTC).year
            text = f"{year}-{date}"
            # The DMY regex permits ``:HH`` or ``:HH:MM`` after the date;
            # JS ``new Date(string)`` happily parses either.  Pick the
            # format Python's ``strptime`` can consume.
            if text.count(":") >= 2:
                fmt = "%Y-%d-%m-%H:%M"
            else:
                fmt = "%Y-%d-%m-%H"
            try:
                return int(_dt.strptime(text, fmt).replace(tzinfo=UTC).timestamp() * 1000)
            except ValueError:
                return int(_time.time() * 1000)
        if date:
            return _parse_freeform(date)
        return int(_time.time() * 1000)

    # -- getDateNumber / fromDateNumber ------------------------------------

    @staticmethod
    def getDateNumber(date: float | None = None, offset: int | None = None) -> int:
        """Return the integer day-number index for ``date``.

        Mirrors ``Math.floor((date.valueOf() / minute - offset) / 1440)``.
        Default ``date`` is now; default ``offset`` is the cached one.
        Returns ``int`` (the floored day count).
        """
        if date is None:
            ms_value: float = _time.time() * 1000
        elif hasattr(date, "valueOf"):
            ms_value = float(date.valueOf())  # type: ignore[attr-defined]
        else:
            ms_value = float(date)  # type: ignore[arg-type]
        if offset is None:
            offset = Time._timezone_offset
        return math.floor((ms_value / Time.minute - offset) / 1440)

    @staticmethod
    def fromDateNumber(value: int, offset: int | None = None) -> int:
        """Inverse of :func:`getDateNumber`. Returns ``int`` ms since epoch.

        Mirrors ``new Date(+new Date(value * day) + offset * minute)``.
        """
        if offset is None:
            offset = Time._timezone_offset
        return int(_round(value * Time.day + offset * Time.minute))

    # -- format ------------------------------------------------------------

    @staticmethod
    def format(ms: float) -> str:
        """Render a duration in the largest natural unit.

        Matches the TS branch order with JS-style rounding.

        - ``>= day - hour/2`` (23.5 h) → days
        - ``>= hour - minute/2`` (59 min) → hours
        - ``>= minute - second/2`` (59 s) → minutes
        - ``>= second`` (1000 ms) → seconds
        - otherwise → ``<ms>ms``
        """
        abs_ms = abs(ms)
        if abs_ms >= Time.day - Time.hour / 2:
            return f"{int(_round(ms / Time.day))}d"
        if abs_ms >= Time.hour - Time.minute / 2:
            return f"{int(_round(ms / Time.hour))}h"
        if abs_ms >= Time.minute - Time.second / 2:
            return f"{int(_round(ms / Time.minute))}m"
        if abs_ms >= Time.second:
            return f"{int(_round(ms / Time.second))}s"
        return f"{int(ms)}ms"

    # -- toDigits ----------------------------------------------------------

    @staticmethod
    def toDigits(source: int, length: int = 2) -> str:
        """Left-pad ``source`` to ``length`` zero-padded digits.

        Mirrors ``source.toString().padStart(length, '0')`` — never truncates
        values that exceed the target width.
        """
        return str(source).rjust(length, "0")

    # -- template ----------------------------------------------------------

    @staticmethod
    def template(template: str, time: _dt | None = None) -> str:
        """Expand Y/M/D/H/M/S placeholders against ``time`` (default: now)."""
        if time is None:
            time = _dt.now(tz=UTC)
        return (
            template.replace("yyyy", str(time.year))
            .replace("yy", str(time.year)[-2:])
            .replace("MM", Time.toDigits(time.month))
            .replace("dd", Time.toDigits(time.day))
            .replace("hh", Time.toDigits(time.hour))
            .replace("mm", Time.toDigits(time.minute))
            .replace("ss", Time.toDigits(time.second))
            .replace("SSS", Time.toDigits(time.microsecond // 1000, 3))
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_NUMERIC = r"\d+(?:\.\d+)?"

_TIME_PATTERN = re.compile(
    rf"^(?:({_NUMERIC})w(?:eek(?:s)?)?)?"
    rf"(?:({_NUMERIC})d(?:ay(?:s)?)?)?"
    rf"(?:({_NUMERIC})h(?:our(?:s)?)?)?"
    rf"(?:({_NUMERIC})m(?:in(?:ute)?(?:s)?)?)?"
    rf"(?:({_NUMERIC})s(?:ec(?:ond)?(?:s)?)?)?$"
)

_TIME_PATTERN_HMS = re.compile(r"^\d{1,2}(:\d{1,2}){1,2}$")
_TIME_PATTERN_DMY = re.compile(r"^\d{1,2}-\d{1,2}-\d{1,2}(:\d{1,2}){1,2}$")


def _parse_freeform(text: str) -> int:
    """Pass through ``text`` to Python's lenient ISO parsing.

    Mirrors ``new Date(text)`` which accepts a wide variety of date formats.
    """
    try:
        # Python 3.11+ is strict about offsets; tolerate strings that end
        # with ``Z`` by converting to ``+00:00``.
        normalised = text.replace("Z", "+00:00") if text.endswith("Z") else text
        parsed = _dt.fromisoformat(normalised)
        return int(parsed.timestamp() * 1000)
    except ValueError:
        return int(_time.time() * 1000)


__all__ = ["Time"]
