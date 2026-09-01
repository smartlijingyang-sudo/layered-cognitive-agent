"""Legacy dual-handler surface for the runs carrier (RETIRED — ADR-0163).

Before ADR-0163 this module provided a parallel handler set that drove the
Session Spine (RunRegistry-driven) instead of the composition-selected
RunPort. The duplicate implementation has been removed; the module is
preserved as a sibling re-export stub so that ``mock.patch`` paths of the
form ``lca.plugins.transport.webserver.handlers.runs.api.routes.<sub>.X``
continue to resolve (see :mod:`lca.plugins.transport.webserver.handlers.runs.api.__init__`).
For the live HTTP surface use:

- :func:`lca.plugins.transport.webserver.handlers.runs.api.command_endpoints.create_run`
  → ``POST /runs`` (RunPort dispatch).
- :func:`lca.plugins.transport.webserver.handlers.runs.api.command_endpoints.cancel_run`
- :func:`lca.plugins.transport.webserver.handlers.runs.api.command_endpoints.answer_run`
- :func:`lca.plugins.transport.webserver.handlers.runs.api.query_endpoints.stream_journal_live`
- :func:`lca.plugins.transport.webserver.handlers.runs.api.query_endpoints.stream_run_live`
- :func:`lca.plugins.transport.webserver.handlers.runs.api.query_endpoints.get_run`
- :func:`lca.plugins.transport.webserver.handlers.runs.api.query_endpoints.get_run_doctor`

The retained inflight-run ``create_run`` helper lives, unrouteable, at
:func:`lca.plugins.transport.webserver.handlers.runs.api.legacy_create_run.create_run`
for any future restore (see ADR-0163 决策 6).
"""

from __future__ import annotations

# ADR-0163 决策 5: sibling re-exports for mock.patch compat. Do not remove
# without updating tests/test_routes_runs_sessions.py and tests/test_run_*_sse.py
# patch strings.
from lca.plugins.transport.webserver.handlers.runs.api import (
    attachment_staging,
    command_endpoints,
    file_reference_parsing,
    query_endpoints,
)

# Expose submodules as attributes on this module so that
# ``lca.plugins.transport.webserver.handlers.runs.api.routes.<sub>.X`` patch
# strings resolve to the real implementation.
command_endpoints = command_endpoints
query_endpoints = query_endpoints
attachment_staging = attachment_staging
file_reference_parsing = file_reference_parsing

__all__ = [
    "attachment_staging",
    "command_endpoints",
    "file_reference_parsing",
    "query_endpoints",
]
