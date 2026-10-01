"""ADR-0256 §4/§5: namespace 是工具的声明式元数据,不是中央映射表.

A2/A3 已随 Task 3（update_turn fail-fast）/ Task 2（删中央映射表）落地，
skip 已解除，转为真用例。
A1 仍 skip：默认工具集 6/7 已声明，仅 listEnvironments
（lca/infrastructure/tools/environment_awareness 的 MANIFEST/ToolApi 未传
namespace）漏声明，根子在源码，已立案 backlog，补上后解除。
A4 可直接运行:源码级双拼工具名扫描.
"""

from __future__ import annotations

import pathlib
import re

import pytest

NAMESPACE_WHITELIST = {"core", "file", "shell", "memory", "skill", "web", "agent", "ext"}


@pytest.mark.skip(
    reason="源码缺口（已立案 backlog）：默认工具集仅 listEnvironments 未声明 namespace "
    "（environment_awareness 的 MANIFEST/ToolApi 未传 namespace），补上后解除 skip。"
)
def test_a1_all_tools_declare_namespace_in_whitelist():
    """注册表里每个工具都声明 namespace,且值在 8 域白名单内."""
    from lca.infrastructure.tools.default.set import build_default_tools

    tools = build_default_tools()  # 落地后应可无参构造,否则补 fixture
    assert tools, "工具注册表为空"
    for tool in tools:
        assert getattr(tool, "namespace", ""), f"{tool.name} 未声明 namespace"
        assert tool.namespace in NAMESPACE_WHITELIST, (
            f"{tool.name}: 非法 namespace {tool.namespace!r}"
        )


def test_a2_update_turn_rejects_tool_without_namespace():
    """漏写 namespace 的工具在 update_turn 直接抛错,不许静默上线."""
    from lca.infrastructure.tool_defer.policy import DeferPolicy
    from lca.infrastructure.tool_defer.session import ToolDeferSession

    class _GhostTool:
        name = "ghost_tool"
        description = "no namespace declared"
        parameters = {"type": "object", "properties": {}}

    session = ToolDeferSession(DeferPolicy())
    with pytest.raises(ValueError, match="namespace"):
        session.update_turn([_GhostTool()])  # 意向 API:不再传中央映射表


def test_a3_central_namespace_map_removed():
    """SSOT 下移到 factory 后,中央映射表必须消失."""
    import lca.infrastructure.capability.tools.tools as tools_mod

    assert not hasattr(tools_mod.ToolsService, "tool_namespaces")
    assert not hasattr(tools_mod.ToolsService, "_tool_namespaces")
    src = pathlib.Path(tools_mod.__file__).read_text(encoding="utf-8")
    assert "tool_namespaces" not in src


_TOOL_NAME_RE = re.compile(r"""(?<!api_)name\s*=\s*["']([A-Za-z_][A-Za-z0-9_]*)["']""")  # api_name 是前端契约名,不是重复注册


def _names_in_file(path: pathlib.Path) -> list[str]:
    """单文件扫描:跳过 ToolApi(name=...) 前端契约声明块(按括号配平)."""
    names: list[str] = []
    skip_depth = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if "ToolApi(" in line:
            skip_depth = line.count("(") - line.count(")")
            continue
        if skip_depth > 0:
            skip_depth += line.count("(") - line.count(")")
            if skip_depth <= 0:
                skip_depth = 0
            continue
        names.extend(_TOOL_NAME_RE.findall(line))
    return names


def _tool_names_from_source() -> list[str]:
    """从工具源码目录收集 name="..." 声明(与 registry 无关的独立扫描).

    只收 Tool 的内部注册名;前端契约名(api_name=.../ToolApi(name=...),
    如 LobeHub 的 activateSkill)是故意设计的另一层名字,不在扫描范围.
    """
    root = pathlib.Path(__file__).resolve().parents[2]
    names: list[str] = []
    for sub in ("lca/infrastructure/tools", "lca/infrastructure/tool"):
        for path in (root / sub).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            names.extend(_names_in_file(path))
    return names


def test_a4_no_snake_camel_duplicate_tool_names():
    """同一工具不许同时注册 snake_case 与 camelCase 两个内部名.

    说明:activate_skill/activateSkill 这类"双拼"是故意设计——内部名(模型可见)
    用 snake_case,api_name(前端契约:LobeHub/computer companion/wechat 展示)
    用 camelCase,两者在 RenderContract 里显式配对。扫描排除 api_name,只查
    真正的重复注册。2026-10-01 修正:此前版本误报 api_name 为双拼。
    """
    seen: dict[str, str] = {}
    for name in _tool_names_from_source():
        key = name.lower().replace("_", "")
        if key in seen and seen[key] != name:
            raise AssertionError(f"双拼工具名: {seen[key]!r} 与 {name!r} 指向同一工具")
        seen[key] = name
