"""工作面梯子（ADR-0248 §6）纯函数策略测试。"""

from lca.infrastructure.work_surface.ladder import (
    LADDER_ORDER,
    WorkSurface,
    order_tools_by_ladder,
    rank_work_surfaces,
    surface_for_tool,
)


def _tool(name: str) -> object:
    class _T:
        def __init__(self, tool_name: str) -> None:
            self.name = tool_name

    return _T(name)


def test_ladder_order_matches_adr() -> None:
    assert LADDER_ORDER == (
        WorkSurface.MEMORY,
        WorkSurface.BOX_FILES,
        WorkSurface.CONNECTORS,
        WorkSurface.WEB_SEARCH,
        WorkSurface.BOX_BROWSER,
        WorkSurface.BOX_GUI,
        WorkSurface.HAND_TO_USER,
    )


def test_rank_work_surfaces_defaults_to_full_ladder() -> None:
    assert rank_work_surfaces() == LADDER_ORDER


def test_rank_work_surfaces_filters_available() -> None:
    ranked = rank_work_surfaces({WorkSurface.BOX_FILES, WorkSurface.WEB_SEARCH})
    assert ranked == (WorkSurface.BOX_FILES, WorkSurface.WEB_SEARCH)


def test_surface_for_tool_mappings() -> None:
    assert surface_for_tool("memory_search") is WorkSurface.MEMORY
    assert surface_for_tool("box_read_file") is WorkSurface.BOX_FILES
    assert surface_for_tool("runCommand") is WorkSurface.BOX_FILES
    assert surface_for_tool("mcp__github__list_repos") is WorkSurface.CONNECTORS
    assert surface_for_tool("connector_install") is WorkSurface.CONNECTORS
    assert surface_for_tool("search") is WorkSurface.WEB_SEARCH
    assert surface_for_tool("web_search") is WorkSurface.WEB_SEARCH
    assert surface_for_tool("browser_navigate") is WorkSurface.BOX_BROWSER
    assert surface_for_tool("askUserQuestion") is WorkSurface.HAND_TO_USER
    assert surface_for_tool("request_box_help") is WorkSurface.HAND_TO_USER
    assert surface_for_tool("unknown_tool") is None


def test_order_tools_by_ladder_puts_low_rungs_first() -> None:
    tools = [
        _tool("askUserQuestion"),
        _tool("web_search"),
        _tool("box_read_file"),
        _tool("memory_add"),
    ]
    ordered = order_tools_by_ladder(tools)
    assert [t.name for t in ordered] == [
        "memory_add",
        "box_read_file",
        "web_search",
        "askUserQuestion",
    ]


def test_order_tools_by_ladder_is_stable_for_unknown() -> None:
    tools = [_tool("zzz_unknown"), _tool("box_write_file"), _tool("aaa_unknown")]
    ordered = order_tools_by_ladder(tools)
    assert [t.name for t in ordered] == ["box_write_file", "zzz_unknown", "aaa_unknown"]
