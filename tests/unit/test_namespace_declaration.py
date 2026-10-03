"""ADR-0256 §4/§5: namespace 是工具的声明式元数据,不是中央映射表.

A2/A3 已随 Task 3 / Task 2 落地，skip 已解除，转为真用例。
A2 契约语义已随 6d190d51b 修订：漏声明 namespace 的工具在 update_turn 不再
硬崩（fail-soft：归入 "unknown" 伪 namespace、只露目录、warning 留痕，发现层面
fail-closed），fail-fast 收敛到 wiring time（ToolsService.register 抛 ValueError）
与 B2（policy 无描述的已声明 namespace 在 update_turn 仍抛错）。
A1 已解除 skip：默认工具集全部声明 namespace，含 listEnvironments
（environment_awareness 的 MANIFEST/ToolApi 已补 namespace="core"）。
A4 可直接运行:源码级双拼工具名扫描.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any, ClassVar

import pytest

from lca.infrastructure.tool_defer.policy import STANDARD_NAMESPACES

# 白名单即源码 SSOT，不手写第二份：
# ADR-0256 8 域（core/file/shell/memory/skill/web/agent/ext）
# + ADR-0268 §4 lca/cron + ADR-0269 §4 avatar。
NAMESPACE_WHITELIST = set(STANDARD_NAMESPACES)


def test_a1_all_tools_declare_namespace_in_whitelist():
    """注册表里每个工具都声明 namespace,且值在标准域白名单内（SSOT 见 STANDARD_NAMESPACES）."""
    from lca.infrastructure.tools.default.set import build_default_tools

    tools = build_default_tools()  # 落地后应可无参构造,否则补 fixture
    assert tools, "工具注册表为空"
    for tool in tools:
        assert getattr(tool, "namespace", ""), f"{tool.name} 未声明 namespace"
        assert tool.namespace in NAMESPACE_WHITELIST, (
            f"{tool.name}: 非法 namespace {tool.namespace!r}"
        )


def test_a2_missing_namespace_is_failsoft_not_silent(caplog):
    """漏写 namespace 的工具在 update_turn 走 fail-soft（6d190d51b 修订语义），
    而不是静默上线：归入 "unknown" 伪 namespace、只露目录、warning 留痕。
    硬 fail-fast 契约由 tests/infrastructure/tool_defer/test_update_turn_failsoft.py
    与 tests/infrastructure/capability/tools/test_register_namespace_failfast.py 承载。
    """
    from lca.infrastructure.tool_defer.policy import DeferPolicy
    from lca.infrastructure.tool_defer.session import ToolDeferSession

    class _GhostTool:
        name = "ghost_tool"
        description = "no namespace declared"
        parameters: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    session = ToolDeferSession(DeferPolicy())
    with caplog.at_level("WARNING"):
        session.update_turn([_GhostTool()])  # 意向 API:不再传中央映射表，不再抛错
    assert any(
        "ghost_tool" in rec.getMessage() and "no namespace" in rec.getMessage()
        for rec in caplog.records
    ), "缺失 namespace 的工具应留 warning 痕迹"


def test_a3_central_namespace_map_removed():
    """SSOT 下移到 factory 后,中央映射表必须消失."""
    import lca.infrastructure.capability.tools.tools as tools_mod

    assert not hasattr(tools_mod.ToolsService, "tool_namespaces")
    assert not hasattr(tools_mod.ToolsService, "_tool_namespaces")
    src = pathlib.Path(tools_mod.__file__).read_text(encoding="utf-8")
    assert "tool_namespaces" not in src


def test_b1_profile_reachable_tools_declare_namespace():
    """web-standard 工具集曾漏声明的工具全部有合法 namespace.

    回归 run_a0e202c1da18：fail-fast 校验在 tool.fork.dispatch 处因
    listEnvironments 空 namespace 抛 ValueError，同 run 工具集里还有
    MCP / composio / assistant 工具同样未声明。逐一断言补完。
    """
    from lca.contracts.models.mcp.types import MCPTool
    from lca.infrastructure.mcp.bridge import adapt_mcp_tool_to_lca
    from lca.infrastructure.tools.assistant.create_skill_tool import AssistantCreateSkillTool
    from lca.infrastructure.tools.assistant.create_tool import AssistantCreateTool
    from lca.infrastructure.tools.assistant.role_card_tool import RoleCardListTool
    from lca.infrastructure.tools.assistant.self_manage_tools import ListAssistantSkillsTool
    from lca.infrastructure.tools.composio import MANAGEMENT_MANIFEST
    from lca.infrastructure.tools.environment_awareness import MANIFEST as ENV_MANIFEST
    from lca.infrastructure.tools.environment_awareness import build_tools as build_env_tools
    from lca.infrastructure.tools.lca_sandbox import MANIFEST as SANDBOX_MANIFEST
    from lca.infrastructure.tools.write_file import MANIFEST as WRITE_MANIFEST
    from lca.plugins.tools.bash import MANIFEST as BASH_MANIFEST
    from lca.plugins.tools.cordis_control.tool import MANIFEST as CORDIS_MANIFEST
    from lca.plugins.tools.file_write import MANIFEST as FILE_WRITE_MANIFEST
    from lca.plugins.tools.profile_apply import MANIFEST as PROFILE_APPLY_MANIFEST
    from lca.plugins.tools.profile_diff import MANIFEST as PROFILE_DIFF_MANIFEST

    # environment awareness → core（平面无关的内置推理原语，保持 eager）
    assert ENV_MANIFEST.api[0].namespace == "core"
    assert build_env_tools(catalog=None)[0].namespace == "core"

    # MCP bridge → ext（第三方集成）
    class _FakeMgr:
        def execute_tool(self, *args: object, **kwargs: object) -> object:
            raise NotImplementedError

    mcp_tool = adapt_mcp_tool_to_lca(
        _FakeMgr(),
        MCPTool(
            name="x",
            server_name="srv",
            qualified_name="srv_x",
            description="d",
            input_schema={},
        ),
    )
    assert mcp_tool.namespace == "ext"

    # composio → ext（第三方集成）
    assert all(api.namespace == "ext" for api in MANAGEMENT_MANIFEST.api)

    # assistant 管理工具 → agent
    assert AssistantCreateTool.namespace == "agent"
    assert RoleCardListTool.namespace == "agent"
    assert AssistantCreateSkillTool.namespace == "agent"
    assert ListAssistantSkillsTool.namespace == "agent"

    # sandbox / write_file → shell / file
    sandbox_by_name = {api.name: api.namespace for api in SANDBOX_MANIFEST.api}
    assert sandbox_by_name["executeCode"] == "shell"
    assert sandbox_by_name["exportFile"] == "file"
    assert WRITE_MANIFEST.api[0].namespace == "file"

    # creator 插件工具 → shell / file / core
    assert BASH_MANIFEST.api[0].namespace == "shell"
    assert FILE_WRITE_MANIFEST.api[0].namespace == "file"
    assert CORDIS_MANIFEST.api[0].namespace == "core"
    assert PROFILE_APPLY_MANIFEST.api[0].namespace == "core"
    assert PROFILE_DIFF_MANIFEST.api[0].namespace == "core"


_TOOL_NAME_RE = re.compile(
    r"""(?<!api_)name\s*=\s*["']([A-Za-z_][A-Za-z0-9_]*)["']"""
)  # api_name 是前端契约名,不是重复注册


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
