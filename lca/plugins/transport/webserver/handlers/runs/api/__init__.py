"""api subpackage of lca.plugins.transport.webserver.handlers.runs — split per ADR-0105 §11.2.

Tests patch concrete submodules directly (``...api.command_endpoints.X``,
``...api.query_endpoints.X``). The ADR-0163 sibling-re-export ``routes``
stub was retired after all ``mock.patch`` paths migrated onto the real
submodules; no live surface references it anymore.

Submodule re-exports are lazy (PEP 562): ``command_endpoints`` imports
``...ingest.ingress.ingress`` at module level while ``ingress`` imports
``...api.file_reference_parsing``; eager re-export here would close the
``ingress → api → command_endpoints → ingress`` cycle and break import.
Attribute access (``api.command_endpoints`` / ``from ...api import X``)
resolves the real submodule on first use — same public surface, no cycle.
"""

from __future__ import annotations

import importlib
from typing import Any

_SUBMODULES = (
    "attachment_staging",
    "command_endpoints",
    "file_reference_parsing",
    "query_endpoints",
)

# _SUBMODULES 是 SSOT（__getattr__ 亦用它）；字面量复写会漂移，故保留计算式。
__all__ = list(_SUBMODULES)  # pyright: ignore[reportUnsupportedDunderAll]


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
