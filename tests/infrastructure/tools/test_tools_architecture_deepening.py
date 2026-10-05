"""Tests verifying Assistant Tool Family surface and Tools package hygiene (INV-ARCH-17, INV-ARCH-18)."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_inv_arch_17_assistant_tools_package_exports() -> None:
    """INV-ARCH-17: All assistant tools, filters, and resolvers are exported directly from lca.infrastructure.tools.assistant."""
    import lca.infrastructure.tools.assistant as asst_tools

    # Creation & Skills
    assert hasattr(asst_tools, "AssistantCreateTool")
    assert hasattr(asst_tools, "CREATE_ASSISTANT_TOOL")
    assert hasattr(asst_tools, "AssistantCreateSkillTool")
    assert hasattr(asst_tools, "assistant_create_skill_tool_from_run")

    # Role Cards
    assert hasattr(asst_tools, "RoleCardListTool")
    assert hasattr(asst_tools, "FileRoleCardResolver")

    # Custom & Filter
    assert hasattr(asst_tools, "AssistantCustomTool")
    assert hasattr(asst_tools, "filter_tools_by_assistant")

    # Memory Tools
    assert hasattr(asst_tools, "MemorySearchTool")
    assert hasattr(asst_tools, "MemoryAddTool")
    assert hasattr(asst_tools, "MemoryUpdateTool")
    assert hasattr(asst_tools, "MemoryRemoveTool")
    assert hasattr(asst_tools, "assistant_memory_tools_from_run")

    # Self Manage Tools
    assert hasattr(asst_tools, "ListAssistantSkillsTool")
    assert hasattr(asst_tools, "ReadAssistantSelfConfigTool")
    assert hasattr(asst_tools, "UpdateAssistantSoulTool")
    assert hasattr(asst_tools, "UpdateAssistantUserTool")
    assert hasattr(asst_tools, "assistant_self_manage_tools_from_run")

    # Declarative Assembly Factory
    assert hasattr(asst_tools, "build_assistant_tools")
    assert callable(asst_tools.build_assistant_tools)


def test_inv_arch_17_build_assistant_tools_assembly() -> None:
    """INV-ARCH-17: build_assistant_tools produces the coherent assistant tool suite."""
    from lca.infrastructure.tools.assistant import build_assistant_tools

    mock_catalog = MagicMock()
    mock_bridge = MagicMock()
    mock_resolver = MagicMock()

    # When bindings has no assistant_id
    tools = build_assistant_tools(
        bindings=None,
        catalog=mock_catalog,
        bridge=mock_bridge,
        role_resolver=mock_resolver,
        default_tool_names=["read_file", "search_files"],
    )

    names = [t.name for t in tools]
    assert "create_assistant" in names
    assert "list_role_cards" in names
    # Memory and self_manage are omitted when no assistant_id is bound
    assert "memory_search" not in names
    assert "list_assistant_skills" not in names


def test_inv_arch_18_tools_micro_packages_hygiene() -> None:
    """INV-ARCH-18: lca.infrastructure.tools.default, shield, and tool export their primitives from __init__.py."""
    import lca.infrastructure.tools.default as default_pkg
    import lca.infrastructure.tools.shield as shield_pkg
    import lca.infrastructure.tools.tool as tool_pkg

    # default package exports
    assert hasattr(default_pkg, "build_default_tools")
    assert hasattr(default_pkg, "build_g2a_chat_tools")
    assert hasattr(default_pkg, "SEARCH_SKILL_TOOL")

    # shield package exports
    assert hasattr(shield_pkg, "ToolPitfallShield")
    assert callable(shield_pkg.ToolPitfallShield)

    # tool package exports
    assert hasattr(tool_pkg, "get_current_tool_invocation_id")
    assert hasattr(tool_pkg, "tool_invocation_scope")
