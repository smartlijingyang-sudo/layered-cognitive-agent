"""工作面梯子（ADR-0248 §6）—— 纯函数策略，无副作用。

梯子顺序（从低到高，默认先走低阶工作面）：

1. memory —— 已有记忆、box 文件、先前结果；
2. box_files —— 员工电脑（我的电脑）文件与 Shell；
3. connectors —— 服务连接器（MCP）；
4. web_search —— 公网 WebSearch / WebFetch；
5. box_browser —— 已登录 box 浏览器（computer-use 子代理）；
6. box_gui —— box 桌面 GUI；
7. hand_to_user —— 交还用户。

``order_tools_by_ladder`` 是稳定排序：未知工作面工具保持原有相对顺序排在已知
工作面之后，保证接入后不破坏既有工具集的相对顺序（C8 确定性）。

本模块放在 infrastructure 层，供 ``lca.nodes.concept.tool_fork.dispatch``
直接消费，避免图节点反向依赖 application 层。
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

LADDER_ORDER_TUPLE = (
    "memory",
    "box_files",
    "connectors",
    "web_search",
    "box_browser",
    "box_gui",
    "hand_to_user",
)


class WorkSurface(StrEnum):
    """工作面梯子的一级。"""

    MEMORY = "memory"
    BOX_FILES = "box_files"
    CONNECTORS = "connectors"
    WEB_SEARCH = "web_search"
    BOX_BROWSER = "box_browser"
    BOX_GUI = "box_gui"
    HAND_TO_USER = "hand_to_user"


LADDER_ORDER: tuple[WorkSurface, ...] = tuple(WorkSurface(v) for v in LADDER_ORDER_TUPLE)

_UNKNOWN_RANK: int = len(LADDER_ORDER)


def rank_work_surfaces(available: set[WorkSurface] | None = None) -> tuple[WorkSurface, ...]:
    """返回按梯子排序的工作面。``available`` 为空时返回全量梯子。"""
    if not available:
        return LADDER_ORDER
    return tuple(surface for surface in LADDER_ORDER if surface in available)


def surface_for_tool(tool_name: str) -> WorkSurface | None:
    """把工具名映射到工作面梯子的一级；无法识别的工具返回 ``None``。"""
    name = (tool_name or "").lower()
    if name in {"askuserquestion", "request_box_help"}:
        return WorkSurface.HAND_TO_USER
    if name.startswith("memory_") or name in {"reflect", "remember", "recall"}:
        return WorkSurface.MEMORY
    if _is_box_surface_tool(name):
        return WorkSurface.BOX_FILES
    if name.startswith("mcp__") or "connector" in name or name.startswith("composio"):
        return WorkSurface.CONNECTORS
    if name in {
        "search",
        "web_search",
        "websearch",
        "search_web",
        "search_skill",
        "web_fetch",
        "fetch_url",
    }:
        return WorkSurface.WEB_SEARCH
    if "browser" in name or name in {"computer_use", "navigate", "playwright"}:
        return WorkSurface.BOX_BROWSER
    if "gui" in name or "desktop" in name or "screenshot" in name:
        return WorkSurface.BOX_GUI
    return None


def _is_box_surface_tool(name: str) -> bool:
    if name.startswith("box_"):
        return True
    return name in {
        "bash",
        "run_shell",
        "runcommand",
        "executecode",
        "readfile",
        "writefile",
        "editfile",
        "listfiles",
        "searchfiles",
        "globfiles",
        "grepcontent",
        "movefiles",
        "read_file",
        "write_file",
        "edit_file",
        "list_files",
        "search_files",
        "glob_files",
        "grep_content",
        "move_files",
    }


def order_tools_by_ladder(tools: Sequence[object]) -> list[object]:
    """稳定排序：低阶工作面工具在前，未知工作面工具保持原序在后。"""
    return sorted(tools, key=_tool_ladder_rank)


def _tool_ladder_rank(tool: object) -> int:
    surface = surface_for_tool(str(getattr(tool, "name", "") or ""))
    if surface is None:
        return _UNKNOWN_RANK
    return LADDER_ORDER.index(surface)


__all__ = [
    "LADDER_ORDER",
    "WorkSurface",
    "order_tools_by_ladder",
    "rank_work_surfaces",
    "surface_for_tool",
]
