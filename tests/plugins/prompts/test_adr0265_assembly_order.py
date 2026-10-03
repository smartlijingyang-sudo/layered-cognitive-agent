# -*- coding: utf-8 -*-
"""ADR-0265 系统提示装配顺序契约验收（T1–T4）。

契约依据：ADR-0265 §3（C1 带序 B1–B8、C2 扩展纪律、C3 可选语义分级），
§7 四项已裁决（2026-10-02，李超授权按 muse 思想裁决）。

实证基线（2026-10-03，`_builtin_templates()` 实测）：
- react_prompt 20 段 / routing_prompt 24 段 / hierarchical_prompt 23 段
  （2026-10-02 基线 19/23/22；+1 来自 ADR-0262 C1 的 skill_duty 独立段）；
- routing = react 基座[:13] + 4 team 段 + user_profile/home/autonomous_presets + 尾三段；
  hierarchical = react 基座[:13] + 3 team 段 + 同上（不含 routing 的 4 段）。
"""

from __future__ import annotations

import pytest

from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplateConfig,
    SectionReference,
)
from lca.plugins.prompts.template_provider import (
    _build_provider,
    _builtin_templates,
    Config,
)

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
    "skill_duty": 7,  # 0262 C1: 独立 skill 义务提示块，与 memory_retrieval 同属 B7 行为规则
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
    # 注：§7① 带序重排已由 quality 轮落地（2026-10-03 07:09，merge d27457a13），
    # goal(B2) 回到 backstory(B1) 之后——哨兵同步翻为新顺序。此后模板再倒置
    # 会由 T1 直接钉住，无需哨兵重复覆盖。
    assert react_b1_b5[:4] == ["role", "backstory", "goal", "current_date"]
    assert len(react_b1_b5) == 12
    cur_b1_b5 = [
        name for name, band in _banded_names(template_id) if band <= 5
    ]
    assert cur_b1_b5 == react_b1_b5, (
        f"{template_id}: team 段追加改变了 B1–B5 相对顺序："
        f"{cur_b1_b5} != {react_b1_b5}"
    )


@pytest.mark.parametrize("template_id", _TEMPLATE_IDS)
def test_t1_band_order_no_inversion(template_id: str) -> None:
    """T1：B1–B8 带序不许逆序；带内顺序不锁死。

    ADR-0265 §3 C1：section 必须落在 B1–B8 带内，跨带不许逆序；
    §7① 裁决维持带序（不锁死精确快照——带内顺序可调）。

    历史：2026-10-03 06:09 实测尚有 3 处相邻倒置（goal(B2)->backstory(B1)、vocal_contract(B7)->current_date(B3)、react_tool_usage_guidelines(B7)->user_profile(B4)，后者即 D2；D1 倒置已随 06:09 前移消除）。§7①带序重排已由 quality 轮落地（2026-10-03 07:09，merge d27457a13）——20 段目标顺序落盘后三处倒置全部消除，本测试转绿。实现再次倒置会使本测试变红。
    team 协作段未在 C1 定带，不参与本断言（ADR 缺口，见文件头）。
    """
    banded = _banded_names(template_id)
    inversions = [
        (a, ba, b, bb)
        for (a, ba), (b, bb) in zip(banded, banded[1:])
        if ba > bb
    ]
    assert not inversions, (
        f"{template_id}: band order violated — B1–B8 must not invert: "
        + "; ".join(f"{a}(B{ba}) -> {b}(B{bb})" for a, ba, b, bb in inversions)
    )


def test_t2_profile_extension_before_b1_fails_fast() -> None:
    """T2（契约规格，预期红）：profile 在 B1 之前插段 → 模板加载期抛错。

    ADR-0265 §3 C2 扩展纪律：只许在带内追加；把新段插到 B1 之前
    （或把 B4/B7 的段移到 B5 之前、把 B3 的段改为可选）→ 模板加载期
    报错（fail-fast，与 ADR-0256 wiring-time fail-fast 同一思想）。

    当前 `_build_provider` 无带序校验——profile 配置直接整体替换模板，
    违规不抛错（待实现），故本测试预期红。
    """
    builtin_sections = _builtin_templates()["react_prompt"].sections
    violating = PromptTemplateConfig(
        id="react_prompt",
        variant="react",
        sections=(
            SectionReference(
                name="evil_pre_b1", kind="pure", optional=True, fallback=""
            ),
            *(
                SectionReference(
                    name=ref.name,
                    kind=ref.kind,
                    optional=ref.optional,
                    fallback=ref.fallback,
                )
                for ref in builtin_sections
            ),
        ),
    )
    with pytest.raises(ValueError):
        _build_provider(Config(profile_templates=(violating,)))


@pytest.mark.parametrize("template_id", _TEMPLATE_IDS)
def test_t3_memory_retrieval_required_in_default_templates(template_id: str) -> None:
    """T3（契约规格，预期红）：memory_retrieval 在默认三模板中为必需段。

    ADR-0265 §3 C3 可选语义分级：可选只许用于"能力缺席"（如无 team 时
    teammates 为空），不许用于"义务缺席"——memory_retrieval 承载
    ADR-0260 C2 检索义务决策树，不得为可选；§7④ 裁决改为必需
    （或 profile YAML 显式豁免声明，本测试覆盖默认模板无豁免的情形）。

    当前三模板均为 optional=True（fallback ""）：检索义务在模板层可
    整体静默缺席（D3 模板层盲区）。待 quality lane 落地 §7④。
    """
    template = _builtin_templates()[template_id]
    ref = next(s for s in template.sections if s.name == "memory_retrieval")
    assert ref.optional is False, (
        f"{template_id}: memory_retrieval 必须为必需段"
        f"（ADR-0265 §3 C3 / §7④），当前 optional={ref.optional}"
    )
