"""Production tool set for gateway-composed agents (Phase C + ADR-0044)."""

from __future__ import annotations

from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.tools.default_set import build_default_tools


def production_tools(store: FileStore | None = None) -> list[Tool]:
    """Tools available to gateway / auto-casting agents."""
    return build_default_tools(store)
