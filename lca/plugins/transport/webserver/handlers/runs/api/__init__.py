"""api subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Tests use ``patch("lca.plugins.transport.webserver.handlers.runs.api.routes.command_endpoints.X")`` style
mock paths, which require ``routes`` module to expose the sibling
submodules as attributes. Re-export them here so the test patch surface
keeps loading without touching every test.
"""

from lca.plugins.transport.webserver.handlers.runs.api import (
    attachment_staging,
    command_endpoints,
    file_reference_parsing,
    query_endpoints,
    routes,
)

# Expose submodules as attributes on the routes module so that
# ``lca.plugins.transport.webserver.handlers.runs.api.routes.command_endpoints`` resolves for mock.patch.
routes.command_endpoints = command_endpoints
routes.query_endpoints = query_endpoints
routes.attachment_staging = attachment_staging
routes.file_reference_parsing = file_reference_parsing

# Same exposure on the package itself for ``patch("lca.plugins.transport.webserver.handlers.runs.api.routes.X")``
# paths that target attributes living on the package.
__all__ = [
    "attachment_staging",
    "command_endpoints",
    "file_reference_parsing",
    "query_endpoints",
    "routes",
]
