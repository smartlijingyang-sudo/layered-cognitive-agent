"""doctor subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Public entry points re-exported so callers can use
``from lca.plugins.transport.webserver.handlers.runs.doctor import diagnose``.
"""

from lca.plugins.transport.webserver.handlers.runs.doctor.doctor import (
    DoctorReport,
    HopVerdict,
    diagnose,
    diagnose_session,
)
from lca.plugins.transport.webserver.handlers.runs.doctor.models import (
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
