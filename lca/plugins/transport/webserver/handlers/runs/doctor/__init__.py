"""doctor subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Public entry points re-exported so callers can use
``from lca.plugins.transport.webserver.handlers.runs.doctor import diagnose``.

Legacy ``journal.jsonl`` 流式布局已下线;doctor 只支持 ``journal.json``
(step-tree materialization) 与 Session Spine 路径。
"""

from lca.plugins.transport.webserver.handlers.runs.doctor.doctor import (
    diagnose,
    diagnose_session,
)
from lca.plugins.transport.webserver.handlers.runs.doctor.models import (
    OPEN_STATUSES,
    TERMINAL_STATUSES,
    DoctorMode,
    DoctorReport,
    HopVerdict,
    StepScan,
)

__all__ = [
    "OPEN_STATUSES",
    "TERMINAL_STATUSES",
    "DoctorMode",
    "DoctorReport",
    "HopVerdict",
    "StepScan",
    "diagnose",
    "diagnose_session",
]
