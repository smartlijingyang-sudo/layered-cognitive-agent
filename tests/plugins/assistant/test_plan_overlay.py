"""ADR-0242 PR-7 per-agent ``plan.yaml`` 覆盖测试。

覆盖：
- ``PlanOverlay`` schema：未知字段 fail-closed（I-B11）；
- 有效 plan.yaml 解析成功；
- 编译层登记校验：未登记模板 / section / bundle ⇒ ``PlanCompilerError``；
- 有效 overlay 编译：``CompiledRunPlan`` 携带 prompt 覆盖字段，outer plan
  的 ``sub_spec_ref`` 被改写为实验 bundle 路径。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from lca.contracts.models.assistant.plan_overlay import (
    GraphOverride,
    PlanOverlay,
    PromptOverride,
    SectionOverride,
)
from lca.harness.profile.resolve.resolve import resolve_profile
from lca_kernel.plan.plan_compile import PlanCompilerError, compile_plan

REPO = Path(__file__).resolve().parents[3]
WEB_STANDARD = REPO / "profiles" / "web-standard.yaml"


def _valid_plan_yaml() -> str:
    return """\
prompt:
  template: react_prompt
  sections:
    - name: role
    - name: context
      content: "本助理是电商数据分析专家，常用术语：GMV / 转化率。"
graph:
  subgraphs:
    think: bundles/think/think_subgraph.yaml
"""


class TestPlanOverlaySchema:
    def test_unknown_top_level_field_fails_closed(self) -> None:
        with pytest.raises(ValidationError):
            PlanOverlay.model_validate({"prompt": {}, "graph": {}, "bogus": 1})

    def test_unknown_prompt_field_fails_closed(self) -> None:
        with pytest.raises(ValidationError):
            PlanOverlay.model_validate({"prompt": {"template": "react_prompt", "extra": "x"}})

    def test_unknown_section_field_fails_closed(self) -> None:
        with pytest.raises(ValidationError):
            PlanOverlay.model_validate(
                {"prompt": {"sections": [{"name": "role", "content": "x", "extra": "y"}]}}
            )

    def test_unknown_graph_field_fails_closed(self) -> None:
        with pytest.raises(ValidationError):
            PlanOverlay.model_validate({"graph": {"subgraphs": {}, "extra": "x"}})

    def test_empty_overlay_is_valid(self) -> None:
        overlay = PlanOverlay()
        assert overlay.prompt.template is None
        assert overlay.prompt.sections == ()
        assert overlay.graph.subgraphs == {}

    def test_parse_valid_plan_yaml_succeeds(self) -> None:
        overlay = PlanOverlay.model_validate(yaml.safe_load(_valid_plan_yaml()))
        assert overlay.prompt.template == "react_prompt"
        assert [s.name for s in overlay.prompt.sections] == ["role", "context"]
        assert (
            overlay.prompt.sections[1].content
            == "本助理是电商数据分析专家，常用术语：GMV / 转化率。"
        )
        assert overlay.graph.subgraphs["think"] == "bundles/think/think_subgraph.yaml"

    def test_frozen_overlay_rejects_mutation(self) -> None:
        overlay = PlanOverlay()
        with pytest.raises(ValidationError):
            overlay.prompt.template = "react_prompt"  # type: ignore[misc]


class TestRegistrationValidation:
    """登记校验在 compile 层（持有注册表的层），fail-closed（ADR-0242 I-B11）。"""

    @pytest.fixture
    def resolved(self) -> object:
        return resolve_profile(WEB_STANDARD)

    def test_unregistered_template_rejected(self, resolved: object) -> None:
        overlay = PlanOverlay(prompt=PromptOverride(template="not_a_template"))
        with pytest.raises(PlanCompilerError, match="模板未登记"):
            compile_plan(resolved, overlay=overlay)

    def test_unregistered_section_rejected(self, resolved: object) -> None:
        overlay = PlanOverlay(
            prompt=PromptOverride(sections=(SectionOverride(name="custom_context"),))
        )
        with pytest.raises(PlanCompilerError, match="section 未登记"):
            compile_plan(resolved, overlay=overlay)

    def test_unregistered_bundle_rejected(self, resolved: object) -> None:
        overlay = PlanOverlay(
            graph=GraphOverride(subgraphs={"think": "bundles/think/nonexistent.yaml"})
        )
        with pytest.raises(PlanCompilerError, match="bundle 不存在"):
            compile_plan(resolved, overlay=overlay)

    def test_non_bundle_graph_override_rejected(self, resolved: object) -> None:
        overlay = PlanOverlay(
            graph=GraphOverride(subgraphs={"think": "profiles/web-standard.yaml"})
        )
        with pytest.raises(PlanCompilerError, match="不是 v2 bundle graph"):
            compile_plan(resolved, overlay=overlay)

    def test_registered_template_and_sections_accepted(self, resolved: object) -> None:
        overlay = PlanOverlay(
            prompt=PromptOverride(
                template="react_prompt",
                sections=(SectionOverride(name="role"),),
            )
        )
        plan = compile_plan(resolved, overlay=overlay)
        assert plan.prompt_template_id == "react_prompt"
        assert [s.name for s in plan.prompt_section_overrides] == ["role"]


class TestOverlayCompileMerge:
    """有效 overlay 的 L3 编译合并（ADR-0242 D10）。"""

    @pytest.fixture
    def resolved(self) -> object:
        return resolve_profile(WEB_STANDARD)

    def test_prompt_overrides_attached_to_compiled_plan(self, resolved: object) -> None:
        overlay = PlanOverlay(
            prompt=PromptOverride(
                template="react_prompt",
                sections=(
                    SectionOverride(name="role"),
                    SectionOverride(name="context", content="自定义上下文"),
                ),
            )
        )
        plan = compile_plan(resolved, overlay=overlay)
        assert plan.prompt_template_id == "react_prompt"
        assert plan.prompt_section_overrides == (
            SectionOverride(name="role"),
            SectionOverride(name="context", content="自定义上下文"),
        )

    def test_subgraph_override_rewrites_outer_plan_ref(self, resolved: object) -> None:
        """``graph.subgraphs.think`` 必须改写 outer plan 的 ``sub_spec_ref``。"""
        overlay = PlanOverlay(
            graph=GraphOverride(subgraphs={"think": "bundles/act/act_subgraph.yaml"})
        )
        plan = compile_plan(resolved, overlay=overlay)
        graph_spec = plan.graph_spec
        think_node = next(n for n in graph_spec["nodes"] if n.get("id") == "think.main")
        assert think_node["sub_spec_ref"]["plan_ref"] == "bundles/act/act_subgraph.yaml"
        # 未覆盖的 phase 保持原路径
        perceive_node = next(n for n in graph_spec["nodes"] if n.get("id") == "perceive.main")
        assert (
            perceive_node["sub_spec_ref"]["plan_ref"] == "bundles/perceive/perceive_subgraph.yaml"
        )

    def test_no_overlay_graph_spec_unchanged(self, resolved: object) -> None:
        """I-B8：无 overlay 时 graph_spec 与启用前一致。"""
        plan = compile_plan(resolved)
        think_node = next(n for n in plan.graph_spec["nodes"] if n.get("id") == "think.main")
        assert think_node["sub_spec_ref"]["plan_ref"] == "bundles/think/think_subgraph.yaml"
        assert plan.prompt_template_id is None
        assert plan.prompt_section_overrides == ()
