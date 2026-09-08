"""agent_lab ↔ LCA tool adapters.

Re-exports the public ``build_*_tool`` factories that the
``tools/registry.yaml`` YAML references via ``module:Factory`` dotted paths.

Boundary:
  - the registry only ever calls these factory functions
  - the returned ``Tool`` instances are real ``lca.contracts.protocols.Tool``
    (no shim, no proxy, no tool_kind fabrication)
"""

from __future__ import annotations

from agent_lab.adapters.tools.read_file import (
    IDENTIFIER as READ_FILE_ID,
)
from agent_lab.adapters.tools.read_file import (
    MANIFEST as READ_FILE_MANIFEST,
)
from agent_lab.adapters.tools.read_file import (
    ReadFileTool,
    build_read_file_tool,
)

__all__ = [
    "READ_FILE_ID",
    "READ_FILE_MANIFEST",
    "ReadFileTool",
    "build_read_file_tool",
]
