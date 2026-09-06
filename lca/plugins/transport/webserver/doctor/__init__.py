"""Doctor — read-only diagnostics (ADR-0195 §2.4 P3-10).

No repair side effects; passive fold + spine inspection only.
"""

from lca.plugins.transport.webserver.doctor.doctor import (
    diagnose,
    diagnose_session,
)
from lca.plugins.transport.webserver.doctor.models import (
    OPEN_STATUSES,
    TERMINAL_STATUSES,
    DoctorMode,
    DoctorReport,
    HopVerdict,
    StepScan,
)
from lca.plugins.transport.webserver.doctor.step_check import diagnose_step_tree

__all__ = [
    "OPEN_STATUSES",
    "TERMINAL_STATUSES",
    "DoctorMode",
    "DoctorReport",
    "HopVerdict",
    "StepScan",
    "diagnose",
    "diagnose_session",
    "diagnose_step_tree",
]
