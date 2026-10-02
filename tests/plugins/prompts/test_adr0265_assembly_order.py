# -*- coding: utf-8 -*-
"""ADR-0265 系统提示装配顺序契约验收（T1–T4）。

契约依据：ADR-0265 §3（C1 带序 B1–B8、C2 扩展纪律、C3 可选语义分级），
§7 四项已裁决（2026-10-02，李超授权按 muse 思想裁决）。

实证基线（2026-10-02，`_builtin_templates()` 实测）：
- react_prompt 19 段 / routing_prompt 23 段 / hierarchical_prompt 22 段；
- routing = react 基座[:13] + 4 team 段 + user_profile/home/autonomous_presets + 尾三段；
  hierarchical = react 基座[:13] + 3 team 段 + 同上（不含 routing 的 4 段）。
"""

from __future__ import annotations

import pytest

from lca.plugins.prompts.template_provider import _builtin_templates

# ADR-0265 §3 C1 带序（B1–B8）。team 协作段
#（teammates/assigned_roles_text/member_reports_text/routing_instructions/
# member_status_text/evidence_pack_text/hierarchical_instructions）未在 C1 定带，
# 此处不作断言（ADR 缺口，T4 覆盖其追加行为）。
_SECTION_BANDS: dict[str, int] = {
    # B1 宪法层：身份与人格，永不后移
    "role": 1,
    "backstory": 1,
    # B2 任务目标
    "goal": 2,
    # B3 时间锚点：now 的可信来源
    "current_date": 3,
    "developer_timestamp": 3,
    # B4 用户 live 配置：USER CONTEXT 热更新通道
    "user_profile": 4,
    "home": 4,
    "autonomous_presets": 4,
    # B5 能力面
    "tools": 5,
    "cloud_sandbox": 5,
    "available_skills": 5,
    "activated_skills": 5,
    # B6 运行上下文
    "task": 6,
    "context": 6,
    # B7 行为规则
    "react_workflow": 7,
    "react_tool_usage_guidelines": 7,
    "memory_retrieval": 7,
    "vocal_contract": 7,
    # B8 环境尾注
    "runtime_env": 8,
}

_TEMPLATE_IDS = ("react_prompt", "routing_prompt", "hierarchical_prompt")


def _banded_names(template_id: str) -> list[tuple[str, int]]:
    template = _builtin_templates()[template_id]
    return [
        (ref.name, _SECTION_BANDS[ref.name])
        for ref in template.sections
        if ref.name in _SECTION_BANDS
    ]


@pytest.mark.parametrize("template_id", ("routing_prompt", "hierarchical_prompt"))
def test_t4_team_sections_preserve_b1_b5_order(template_id: str) -> None:
    """T4：routing/hierarchical 的 team 段追加不改变 B1–B5 的相对顺序。

    team 段以"基座[:13] 后拼接"方式追加（routing 4 段、hierarchical 3 段，
    均在 user_profile 之前插入）；B1–B5 段全部落在基座[:13] 内，
    其相对顺序必须与 react_prompt 完全一致。改动拼接位置会使本测试变红。
    """
    react_b1_b5 = [
        name for name, band in _banded_names("react_prompt") if band <= 5
    ]
    # 完整性哨兵：防止测试空转（B1-B5 共 12 段；模板增删段时此数会变，
    # 此时应同步复核本测试而非静默放过）。
    assert react_b1_b5[:4] == ["role", "goal", "backstory", "current_date"]
    assert len(react_b1_b5) == 12
    cur_b1_b5 = [
        name for name, band in _banded_names(template_id) if band <= 5
    ]
    assert cur_b1_b5 == react_b1_b5, (
        f"{template_id}: team 段追加改变了 B1–B5 相对顺序："
        f"{cur_b1_b5} != {react_b1_b5}"
    )
