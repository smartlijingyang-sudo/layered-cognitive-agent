"""api subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Tests use ``patch("lca.plugins.transport.webserver.handlers.runs.api.routes.<sub>.X")``
and ``patch("lca.plugins.transport.webserver.handlers.runs.api.<sub>.X")`` style
mock paths. Both forms resolve here:

- The ``lca.plugins.transport.webserver.handlers.runs.api.routes`` module is
  a sibling-re-export stub (see ADR-0163 决策 5) that exposes every concrete
  submodule as an attribute, so a patch path targeting
  ``...api.routes.<sub>.X`` finds the real implementation.
- The package itself re-exports the same submodules so patch paths targeting
  ``...api.<sub>.X`` resolve directly.

ADR-0163 决策 6 deletes the inflight-run dedupe path entirely; nothing in
this package retains Session-Spine dual-handler state.
"""

from lca.plugins.transport.webserver.handlers.runs.api import (
    attachment_staging,
    command_endpoints,
    file_reference_parsing,
    query_endpoints,
    routes,
)

routes.command_endpoints = command_endpoints
routes.query_endpoints = query_endpoints
routes.attachment_staging = attachment_staging
routes.file_reference_parsing = file_reference_parsing

__all__ = [
    "attachment_staging",
    "command_endpoints",
    "file_reference_parsing",
    "query_endpoints",
    "routes",
]
