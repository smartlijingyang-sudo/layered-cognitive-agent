"""ADR-0248 声带契约 prompt section 测试。

验证：
- gated 模式渲染声带契约 + Reply-First 提醒；
- 已 Ack 后只保留契约、不再提醒；
- direct（默认）模式零侵入返回空；
- 提示词正文来自资源文件（非 Python 硬编码字符串）；
- 内建模板包含 vocal_contract section 引用。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    reset_capability_bindings,
    set_capability_bindings,
)
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool import SendMessageTool
from lca.plugins.prompts.sections import (
    VocalContractSection,
    build_vocal_contract,
)

_CONTRACT = "CONTRACT-TEXT"
_REMINDER = "REMINDER-TEXT"


def _render(section: VocalContractSection) -> SectionOutput:
    return section.render(
        role_profile=None,  # type: ignore[arg-type]
        task="t",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )


def _gated_bindings(gate: GatedVocalGate) -> Any:
    return BindingsViewBuilder(vocal_mode="gated", vocal_gate=gate)


def test_gated_renders_contract_and_reply_first_reminder() -> None:
    gate = GatedVocalGate("op_gated")
    token = set_capability_bindings(_gated_bindings(gate))
    try:
        out = _render(VocalContractSection(_CONTRACT, _REMINDER))
    finally:
        reset_capability_bindings(token)

    assert _CONTRACT in out.text
    assert _REMINDER in out.text
    assert "vocal_contract" in out.text


def test_gated_after_ack_keeps_contract_drops_reminder() -> None:
    gate = GatedVocalGate("op_acked")
    SendMessageTool(gate).execute(type="text", content="正在处理...")
    assert gate.has_acked is True

    token = set_capability_bindings(_gated_bindings(gate))
    try:
        out = _render(VocalContractSection(_CONTRACT, _REMINDER))
    finally:
        reset_capability_bindings(token)

    assert _CONTRACT in out.text
    assert _REMINDER not in out.text


def test_direct_mode_returns_empty() -> None:
    out = _render(VocalContractSection(_CONTRACT, _REMINDER))
    assert out.text == ""


def test_contract_text_comes_from_prompt_resource_files() -> None:
    """正文来自 lca/cognition/brain/prompts/*.md，而非 Python 字符串常量。"""
    from lca.cognition.brain.prompts._loader import load_builtin_prompt

    contract = load_builtin_prompt("vocal_contract")
    reminder = load_builtin_prompt("reply_first_reminder")
    assert "send_message" in contract
    assert "Reply-First" in reminder


def test_build_vocal_contract_loads_resource_defaults() -> None:
    section = build_vocal_contract(type("_Cfg", (), {"instruction_overrides": {}})())
    out = _render(section)
    # 未配置 bindings → 空（说明默认文本已加载但不渲染）
    assert out.text == ""
    assert section._contract_text
    assert "send_message" in section._contract_text


def test_builtin_templates_include_vocal_contract_ref() -> None:
    from lca.plugins.prompts.template_provider import _builtin_templates

    for tpl in _builtin_templates().values():
        names = {ref.name for ref in tpl.sections}
        assert "vocal_contract" in names
