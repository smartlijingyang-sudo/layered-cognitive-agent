"""Render contract definitions, registry, and codegen for tool→renderer mapping."""

from lca.infrastructure.tools.contract.builtin import (
    sandbox_state,
    skill_args,
    skill_state,
)
from lca.infrastructure.tools.contract.codegen_ts import render_registry_to_ts
from lca.infrastructure.tools.contract.project import (
    project_args,
    project_content,
    project_full,
    project_tool_state,
)
from lca.infrastructure.tools.contract.render import (
    REGISTRY,
    FieldSpec,
    RenderContract,
    contract,
    get_contract,
)
from lca.infrastructure.tools.contract.sandbox_contracts import (  # noqa: F401  — registers dynamic tools
    _ALL as _SANDBOX_ALL,
)
from lca.infrastructure.tools.contract.schema import COMMON

__all__ = [
    "COMMON",
    "REGISTRY",
    "FieldSpec",
    "RenderContract",
    "contract",
    "get_contract",
    "project_args",
    "project_content",
    "project_full",
    "project_tool_state",
    "render_registry_to_ts",
    "sandbox_state",
    "skill_args",
    "skill_state",
]
