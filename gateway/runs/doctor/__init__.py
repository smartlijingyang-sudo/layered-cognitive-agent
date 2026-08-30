"""doctor subpackage of gateway.runs — split per ADR-0105 §11.2.

Public entry points re-exported so callers can use
``from gateway.runs.doctor import diagnose``.
"""

from gateway.runs.doctor.doctor import (
    DoctorReport,
    HopVerdict,
    diagnose,
    diagnose_session,
)
from gateway.runs.doctor.models import (
    RUN_FINISHED_EVENTS,
    TOOL_TERMINAL_EVENTS,
    JsonlScan,
)

__all__ = [
    "RUN_FINISHED_EVENTS",
    "TOOL_TERMINAL_EVENTS",
    "DoctorReport",
    "HopVerdict",
    "JsonlScan",
    "diagnose",
    "diagnose_session",
]
