"""Auto-generated surface skeleton for upstream ``schedule/schedule/src/domain.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``schedule/schedule/src/domain.ts``
"""


from __future__ import annotations
from typing import Protocol, TypeAlias

__all__: list[str] = [
    "EveryOccurrence",
    "FoldedSchedules",
    "MIN_EVERY_INTERVAL_SECONDS",
    "SCHEDULE_CHANGE_VERSION",
    "ScheduleId",
    "ScheduleInputError",
    "ScheduleLogError",
    "allocateScheduleId",
    "canonicalizeTimeZone",
    "createAfterScheduleRecord",
    "createAtScheduleRecord",
    "createEveryScheduleRecord",
    "decodeScheduleChange",
    "foldScheduleEvents",
    "renderEveryReminderBatchFraming",
    "renderReminderFraming",
    "resolveEveryOccurrence",
    "scheduleView",
]

MIN_EVERY_INTERVAL_SECONDS = None  # port: surface stub

SCHEDULE_CHANGE_VERSION = None  # port: surface stub

def ScheduleId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``ScheduleId``."""
    raise NotImplementedError("port ScheduleId from schedule/schedule/src/domain.ts")

def allocateScheduleId(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``allocateScheduleId``."""
    raise NotImplementedError("port allocateScheduleId from schedule/schedule/src/domain.ts")

def canonicalizeTimeZone(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``canonicalizeTimeZone``."""
    raise NotImplementedError("port canonicalizeTimeZone from schedule/schedule/src/domain.ts")

def createAfterScheduleRecord(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createAfterScheduleRecord``."""
    raise NotImplementedError("port createAfterScheduleRecord from schedule/schedule/src/domain.ts")

def createAtScheduleRecord(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createAtScheduleRecord``."""
    raise NotImplementedError("port createAtScheduleRecord from schedule/schedule/src/domain.ts")

def createEveryScheduleRecord(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``createEveryScheduleRecord``."""
    raise NotImplementedError("port createEveryScheduleRecord from schedule/schedule/src/domain.ts")

def decodeScheduleChange(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``decodeScheduleChange``."""
    raise NotImplementedError("port decodeScheduleChange from schedule/schedule/src/domain.ts")

def foldScheduleEvents(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``foldScheduleEvents``."""
    raise NotImplementedError("port foldScheduleEvents from schedule/schedule/src/domain.ts")

def renderEveryReminderBatchFraming(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderEveryReminderBatchFraming``."""
    raise NotImplementedError("port renderEveryReminderBatchFraming from schedule/schedule/src/domain.ts")

def renderReminderFraming(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``renderReminderFraming``."""
    raise NotImplementedError("port renderReminderFraming from schedule/schedule/src/domain.ts")

def resolveEveryOccurrence(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``resolveEveryOccurrence``."""
    raise NotImplementedError("port resolveEveryOccurrence from schedule/schedule/src/domain.ts")

def scheduleView(*args: object, **kwargs: object) -> object:
    """Surface stub for upstream function ``scheduleView``."""
    raise NotImplementedError("port scheduleView from schedule/schedule/src/domain.ts")

class ScheduleInputError:
    """Surface stub for upstream class ``ScheduleInputError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ScheduleInputError.__init__ from schedule/schedule/src/domain.ts")

class ScheduleLogError:
    """Surface stub for upstream class ``ScheduleLogError``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError("port ScheduleLogError.__init__ from schedule/schedule/src/domain.ts")

class EveryOccurrence(Protocol):
    """Surface stub for upstream interface ``EveryOccurrence``."""
    pass

class FoldedSchedules(Protocol):
    """Surface stub for upstream interface ``FoldedSchedules``."""
    pass
