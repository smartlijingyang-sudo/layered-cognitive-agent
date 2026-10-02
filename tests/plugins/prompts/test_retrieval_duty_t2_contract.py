"""Contract tests for ADR-0260 T2: retrieval-duty prompt-assembly precondition.

T2 原文: 冷门事实问答 run 轨迹——首轮回答前必须出现 memory_search 调用;
直接答对但无检索记录 = 不合格.

硬轨迹门在代码中不存在 (0260 C2 是提示块义务而非强制门; ADR-0260 尾部裁决:
检索义务 fail-open + 标注), fake-model 断言工具序列是测 stub 空转.
本文件钉住 T2 的 prompt 装配级可测内核 (夜战 Track B 提案, 本轮 tests 轮落地):

  (1) 非豁免冷门事实任务装配 react_prompt 首轮 system 时,
      "记忆检索义务"块在场 (home-bound run 渲染完整义务块);
  (2) 义务块点名的 memory_search 与生产 wire 工具名是同一常量
      (工具改名 -> 块内指令悬空, 测试即红);
  (3) wire 工具经 ToolsSection 装配进 system 时, memory_search 确实在目录里;
  (4) 未绑定 home 的 run 渲染显式"无持久记忆可用"声明 (fail-open),
      而非空块 —— 0260 决议 2 的盲区修复 (daae6335e) 钉住.

轨迹级验收 (真实 run 首轮 tool_calls 序列) 仍是 Track B 后续项, 不在本文件范围.
"""
from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.tools.assistant.memory_tools import _MEMORY_SEARCH_TOOL
from lca.plugins.prompts.sections.memory import MemoryRetrievalSection
from lca.plugins.prompts.sections.tools import ToolsSection
from lca.plugins.prompts.template_provider import _builtin_templates

# 非豁免冷门事实任务: 不在豁免清单 (纯寒暄/简短确认/逐字复制/明确要求不查) 内,
# 必须走检索义务.
_COLD_FACT_TASK = "我老婆的表弟叫什么名字"


def _profile(**extra: object) -> RoleProfile:
    return RoleProfile(
        role="助手",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra=extra,
    )


def _render_memory(profile: RoleProfile, task: str = _COLD_FACT_TASK) -> str:
    return (
        MemoryRetrievalSection()
        .render(
            role_profile=profile,
            task=task,
            awareness=None,
            manifest=None,
            tools=(),
            activated_skills=(),
        )
        .text
    )


def test_memory_retrieval_section_in_react_template() -> None:
    names = [ref.name for ref in _builtin_templates()["react_prompt"].sections]
    assert "memory_retrieval" in names, "react_prompt 缺 memory_retrieval 块 (0260 T2 前提)"


def test_duty_block_present_for_home_bound_cold_fact() -> None:
    text = _render_memory(_profile(assistant_home_path="/home/u/.lca/assistants/asst_1"))
    assert "## 记忆检索义务与决策树" in text
    assert "memory_search" in text
    # ADR-0267 凝练后措辞 (5020d807f): 旧字串"至少 3 个角度"已不存在, 钉新措辞防回退
    assert "多角度，首个 query 贴近用户原话" in text
    assert "未检索标注" in text
    assert "绝不编造" in text


def test_duty_block_names_production_wire_tool() -> None:
    """义务块点名的工具名必须等于生产 wire 常量, 否则指令悬空."""
    assert _MEMORY_SEARCH_TOOL == "memory_search"
    text = _render_memory(_profile(assistant_home_path="/home/u/.lca/assistants/asst_1"))
    assert _MEMORY_SEARCH_TOOL in text


def test_unbound_run_declares_no_memory_fail_open() -> None:
    """未绑定 home: 显式声明无记忆可用 (fail-open), 而非空块 —— 0260 决议 2."""
    text = _render_memory(_profile())
    assert text.strip(), "unbound run 渲染出空块 = 义务块静默消失 (0260 C2 盲区回退)"
    assert "无持久记忆可用" in text
    assert "未经检索" in text
    # unbound 变体不得携带 bound-only 的完整义务 (防 _has_home 门回退)
    assert "命中则 memory_explain 精读" not in text


@dataclass(frozen=True)
class _WireTool:
    name: str
    description: str = ""


def test_tools_section_carries_memory_search_onto_prompt() -> None:
    """wire 工具经 ToolsSection 装配进 system 时, memory_search 在目录里."""
    text = (
        ToolsSection()
        .render(
            role_profile=_profile(),
            task=_COLD_FACT_TASK,
            awareness=None,
            manifest=None,
            tools=[_WireTool(name=_MEMORY_SEARCH_TOOL, description="检索记忆")],
            activated_skills=(),
        )
        .text
    )
    assert f'<tool name="{_MEMORY_SEARCH_TOOL}">' in text


def test_tools_section_empty_catalog_renders_nothing() -> None:
    """空工具目录不渲染占位块 —— 与 ToolsSection.docstring 一致 (防幻觉占位)."""
    out = (
        ToolsSection()
        .render(
            role_profile=_profile(),
            task=_COLD_FACT_TASK,
            awareness=None,
            manifest=None,
            tools=[],
            activated_skills=(),
        )
    )
    assert out.text == ""
    assert out.used_fallback is True
