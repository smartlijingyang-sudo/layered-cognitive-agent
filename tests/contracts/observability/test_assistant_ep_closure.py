"""EP closure regression test for ADR-0187 §3 D8 (I-A11).

助理域新增 12 个 EP（``assistant.created`` 等），构成本仓 Spine 事件词表的
闭集扩展。本测试守住三个 PR-2 落点：

1. EP 描述符登记：``assistant_ep_closure.all_assistant_event_descriptors()``
   返回 12 个 ``EventDescriptor`` 元数据，全部登记 ``required`` = 四件套
   （``assistant_id`` / ``revision_seq`` / ``manifest_digest`` / ``actor``）。
2. cordis 事件表映射：12 个 EP 全部走 ``cordis_event_table.lookup_cordis_name``
   派生出 ``"agent.assistant.*"`` 派生名（ADR-0169 L12）。
3. EP 词表本身（``ASSISTANT_EVENT_POINTS``）长度恒等于 12；CI 守护「不增不
   删」（AGENTS.md §3 C1 闭集）。

未来若新增 EP，必须先 ADR + 同步本测试。
"""

from __future__ import annotations

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventSensitivity,
)
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_CORDIS_NAMES,
    ASSISTANT_CREATED,
    ASSISTANT_EVENT_POINTS,
    ASSISTANT_JOB_FIRED,
    ASSISTANT_JOB_REGISTERED,
    ASSISTANT_PAUSED,
    ASSISTANT_PROFILE_REVISED,
    ASSISTANT_REQUIRED_FIELDS,
    ASSISTANT_RESUMED,
    ASSISTANT_RETIRED,
    ASSISTANT_SKILL_ACTIVATED,
    ASSISTANT_SKILL_EVOLVED_PROMOTED,
    ASSISTANT_SKILL_EVOLVED_PROPOSED,
    ASSISTANT_SKILL_INSTALLED,
    all_assistant_event_descriptors,
)
from lca.contracts.observability.cordis_event_table import (
    all_execution_points,
    lookup_cordis_name,
)

# ADR-0187 §3 D8 钉死的 12 EP 集合 — 增减必须先 ADR。
_EXPECTED_EVENT_POINTS: tuple[str, ...] = (
    ASSISTANT_CREATED,
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_PROFILE_REVISED,
    ASSISTANT_PAUSED,
    ASSISTANT_RESUMED,
    ASSISTANT_SKILL_INSTALLED,
    ASSISTANT_SKILL_ACTIVATED,
    ASSISTANT_SKILL_EVOLVED_PROPOSED,
    ASSISTANT_SKILL_EVOLVED_PROMOTED,
    ASSISTANT_JOB_REGISTERED,
    ASSISTANT_JOB_FIRED,
    ASSISTANT_RETIRED,
)


class TestAssistantEventPointClosure:
    """ADR-0187 §3 D8 闭集扩展 —— 长度恒等于 12，元素一一匹配。"""

    def test_closure_has_twelve_entries(self) -> None:
        assert len(ASSISTANT_EVENT_POINTS) == 12

    def test_closure_matches_d8_spec(self) -> None:
        assert ASSISTANT_EVENT_POINTS == _EXPECTED_EVENT_POINTS

    def test_closure_has_no_duplicates(self) -> None:
        assert len(ASSISTANT_EVENT_POINTS) == len(set(ASSISTANT_EVENT_POINTS))

    def test_closure_uses_dot_namespace(self) -> None:
        for ep in ASSISTANT_EVENT_POINTS:
            assert ep.startswith("assistant."), f"{ep!r} 未带 assistant. 前缀"

    def test_required_fields_complete(self) -> None:
        assert ASSISTANT_REQUIRED_FIELDS == (
            "assistant_id",
            "revision_seq",
            "manifest_digest",
            "actor",
        )


class TestAssistantCordisDerivation:
    """cordis 派生表（ADR-0169 L12） —— 全部以 ``agent.assistant.*`` 收口。"""

    def test_cordis_names_cover_closure(self) -> None:
        assert set(ASSISTANT_CORDIS_NAMES) == set(ASSISTANT_EVENT_POINTS)

    def test_cordis_names_have_agent_prefix(self) -> None:
        for ep, cordis in ASSISTANT_CORDIS_NAMES.items():
            assert cordis == f"agent.{ep}", f"{ep!r} → {cordis!r} 未遵守 agent.<ep> 派生规则"

    def test_lookup_cordis_name_resolves_all_eps(self) -> None:
        for ep in ASSISTANT_EVENT_POINTS:
            entry = lookup_cordis_name(ep)
            assert entry.execution_point == ep
            assert entry.cordis_name == f"agent.{ep}"

    def test_cordis_event_table_includes_assistant_eps(self) -> None:
        all_eps = set(all_execution_points())
        for ep in ASSISTANT_EVENT_POINTS:
            assert ep in all_eps, f"{ep!r} 未登记进 cordis 事件表"


class TestAssistantEventDescriptors:
    """PR-2 contracts 层 EP 元数据 —— 12 个 EventDescriptor 元数据已冻结。"""

    def test_descriptor_count_matches_closure(self) -> None:
        descriptors = all_assistant_event_descriptors()
        assert len(descriptors) == len(ASSISTANT_EVENT_POINTS)

    def test_descriptors_are_typed_correctly(self) -> None:
        descriptors = all_assistant_event_descriptors()
        assert all(isinstance(d, EventDescriptor) for d in descriptors)

    def test_each_descriptor_has_required_fields(self) -> None:
        descriptors = {d.type_name: d for d in all_assistant_event_descriptors()}
        for ep in ASSISTANT_EVENT_POINTS:
            descriptor = descriptors[ep]
            assert descriptor.required == ASSISTANT_REQUIRED_FIELDS, (
                f"{ep!r} required={descriptor.required!r} != {ASSISTANT_REQUIRED_FIELDS!r}"
            )

    def test_each_descriptor_is_required_auditor_internal(self) -> None:
        """配置面 EP 全部 durability=required + audience=auditor + sensitivity=internal。"""
        for descriptor in all_assistant_event_descriptors():
            assert descriptor.durability is EventDurability.REQUIRED, descriptor.type_name
            assert descriptor.audience is EventAudience.AUDITOR, descriptor.type_name
            assert descriptor.sensitivity is EventSensitivity.INTERNAL, descriptor.type_name

    def test_emitters_use_assistant_namespace(self) -> None:
        """emitter 一律走 ``lca.plugins.assistant.*`` 命名空间（PR-3 插件前缀对齐）。"""
        for descriptor in all_assistant_event_descriptors():
            assert descriptor.emitter.startswith("lca.plugins.assistant."), (
                f"{descriptor.type_name!r} emitter={descriptor.emitter!r} 未遵守命名空间"
            )

    def test_descriptors_are_immutable(self) -> None:
        descriptor = all_assistant_event_descriptors()[0]
        from dataclasses import FrozenInstanceError

        import pytest

        with pytest.raises(FrozenInstanceError):
            descriptor.type_name = "tampered"  # type: ignore[misc]
