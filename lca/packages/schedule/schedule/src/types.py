"""Auto-generated surface skeleton for upstream ``schedule/schedule/src/types.ts``.

Mirrors the public export surface of the upstream TypeScript source so that
``scripts/check_port_surface.py`` reports parity. Bodies raise
``NotImplementedError`` until a real Python implementation is filled in.

Upstream source: ``schedule/schedule/src/types.ts``
"""


from __future__ import annotations

from typing import Protocol, TypeAlias

__all__: list[str] = [
    "AfterScheduleRecord",
    "AtInput",
    "AtScheduleRecord",
    "CorruptScheduleLogError",
    "EveryScheduleDispatchChange",
    "EveryScheduleRecord",
    "FrequencyTooHighError",
    "InternalScheduleError",
    "InvalidPromptError",
    "InvalidRuleError",
    "InvalidSelectorError",
    "InvalidTimeZoneError",
    "LocalAtInput",
    "NotFutureError",
    "OneShotScheduleDispatchChange",
    "OneShotScheduleRecord",
    "PersistenceUncertainError",
    "ScheduleChange",
    "ScheduleCreateChange",
    "ScheduleCreateValue",
    "ScheduleDeleteChange",
    "ScheduleDeleteResult",
    "ScheduleDeleteValue",
    "ScheduleDeliveryMode",
    "ScheduleDispatchChange",
    "ScheduleId",
    "ScheduleListValue",
    "SchedulePersistenceOperation",
    "ScheduleRecord",
    "ScheduleState",
    "ScheduleToolError",
    "ScheduleView",
    "TimeOutOfRangeError",
]

AtInput: TypeAlias = object  # port: surface stub

OneShotScheduleRecord: TypeAlias = object  # port: surface stub

ScheduleChange: TypeAlias = object  # port: surface stub

ScheduleCreateValue: TypeAlias = object  # port: surface stub

ScheduleDeleteResult: TypeAlias = object  # port: surface stub

ScheduleDeleteValue: TypeAlias = object  # port: surface stub

ScheduleDeliveryMode: TypeAlias = object  # port: surface stub

ScheduleDispatchChange: TypeAlias = object  # port: surface stub

ScheduleId: TypeAlias = object  # port: surface stub

ScheduleListValue: TypeAlias = object  # port: surface stub

SchedulePersistenceOperation: TypeAlias = object  # port: surface stub

ScheduleRecord: TypeAlias = object  # port: surface stub

ScheduleState: TypeAlias = object  # port: surface stub

ScheduleToolError: TypeAlias = object  # port: surface stub

ScheduleView: TypeAlias = object  # port: surface stub

class AfterScheduleRecord(Protocol):
    """Surface stub for upstream interface ``AfterScheduleRecord``."""
    pass

class AtScheduleRecord(Protocol):
    """Surface stub for upstream interface ``AtScheduleRecord``."""
    pass

class CorruptScheduleLogError(Protocol):
    """Surface stub for upstream interface ``CorruptScheduleLogError``."""
    pass

class EveryScheduleDispatchChange(Protocol):
    """Surface stub for upstream interface ``EveryScheduleDispatchChange``."""
    pass

class EveryScheduleRecord(Protocol):
    """Surface stub for upstream interface ``EveryScheduleRecord``."""
    pass

class FrequencyTooHighError(Protocol):
    """Surface stub for upstream interface ``FrequencyTooHighError``."""
    pass

class InternalScheduleError(Protocol):
    """Surface stub for upstream interface ``InternalScheduleError``."""
    pass

class InvalidPromptError(Protocol):
    """Surface stub for upstream interface ``InvalidPromptError``."""
    pass

class InvalidRuleError(Protocol):
    """Surface stub for upstream interface ``InvalidRuleError``."""
    pass

class InvalidSelectorError(Protocol):
    """Surface stub for upstream interface ``InvalidSelectorError``."""
    pass

class InvalidTimeZoneError(Protocol):
    """Surface stub for upstream interface ``InvalidTimeZoneError``."""
    pass

class LocalAtInput(Protocol):
    """Surface stub for upstream interface ``LocalAtInput``."""
    pass

class NotFutureError(Protocol):
    """Surface stub for upstream interface ``NotFutureError``."""
    pass

class OneShotScheduleDispatchChange(Protocol):
    """Surface stub for upstream interface ``OneShotScheduleDispatchChange``."""
    pass

class PersistenceUncertainError(Protocol):
    """Surface stub for upstream interface ``PersistenceUncertainError``."""
    pass

class ScheduleCreateChange(Protocol):
    """Surface stub for upstream interface ``ScheduleCreateChange``."""
    pass

class ScheduleDeleteChange(Protocol):
    """Surface stub for upstream interface ``ScheduleDeleteChange``."""
    pass

class TimeOutOfRangeError(Protocol):
    """Surface stub for upstream interface ``TimeOutOfRangeError``."""
    pass
