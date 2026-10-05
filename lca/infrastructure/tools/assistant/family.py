"""Assistant Tool Family declarative assembly (INV-ARCH-17)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from lca.contracts.protocols import Tool
from lca.infrastructure.tools.assistant.create_skill_tool import (
    assistant_create_skill_tool_from_run,
)
from lca.infrastructure.tools.assistant.create_tool import AssistantCreateTool
from lca.infrastructure.tools.assistant.memory_tools import assistant_memory_tools_from_run
from lca.infrastructure.tools.assistant.role_card_resolver import FileRoleCardResolver
from lca.infrastructure.tools.assistant.role_card_tool import RoleCardListTool
from lca.infrastructure.tools.assistant.self_manage_tools import (
    assistant_self_manage_tools_from_run,
)


def build_assistant_tools(
    bindings: object = None,
    *,
    catalog: Any = None,
    bridge: Any = None,
    overlay: Any = None,
    tool_overlay: Any = None,
    role_resolver: FileRoleCardResolver | None = None,
    default_tool_names: Sequence[str] | Callable[[], Sequence[str]] | None = None,
    catalog_names: Callable[[], list[str]] | None = None,
    profile_backfill: Any = None,
) -> list[Tool]:
    """Declaratively assemble the coherent assistant tool suite for a run."""
    tools: list[Any] = []

    if catalog is not None:
        tools.append(
            AssistantCreateTool(
                catalog=catalog,
                bridge=bridge,
                default_tool_names=default_tool_names,
            )
        )

    if role_resolver is not None:
        tools.append(RoleCardListTool(resolver=role_resolver))

    create_skill = assistant_create_skill_tool_from_run(bindings, overlay=overlay)
    if create_skill is not None:
        tools.append(create_skill)

    tools.extend(
        assistant_self_manage_tools_from_run(
            bindings,
            catalog=catalog,
            overlay=overlay,
            tool_overlay=tool_overlay,
            catalog_names=catalog_names,
        )
    )

    tools.extend(
        assistant_memory_tools_from_run(
            bindings,
            catalog=catalog,
            profile_backfill=profile_backfill,
        )
    )

    return tools
