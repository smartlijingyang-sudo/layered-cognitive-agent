"""api subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Tests patch concrete submodules directly (``...api.command_endpoints.X``,
``...api.query_endpoints.X``). The ADR-0163 sibling-re-export ``routes``
stub was retired after all ``mock.patch`` paths migrated onto the real
submodules; no live surface references it anymore.
"""

from lca.plugins.transport.webserver.handlers.runs.api import (
    attachment_staging,
    command_endpoints,
    file_reference_parsing,
    query_endpoints,
)

__all__ = [
    "attachment_staging",
    "command_endpoints",
    "file_reference_parsing",
    "query_endpoints",
]
