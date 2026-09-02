"""ADR-0169 PR-13:EventDescriptor + cordis_name 派生(L12 / I-CURSOR-4)。

闭合扫查:
- EventDescriptor 是 ``frozen=True``;试图改字段冻结。
- ``derive("phase.think.fold")`` 返回 ``cordis_name == "agent.phase.think.fold"``。
- 全部 7 个 ``PhaseName`` 值都被 cordis_event_table 覆盖。
- 未登记 execution_point ⇒ ``UnknownCordisEventError``(L15 UnknownEventType 同源)。
- ``schema_version`` 字段存在且 ``>= 1``(L15 方向感知 journal 格式拒绝)。
- ``derive()`` 是 deterministic:同 EP 多次派生得到字面相同的 EventDescriptor。
- ``ignorable`` 默认 False 与登记 entries 透传一致。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from lca.contracts.observability.cordis_event_table import (
    CordisEventTableEntry,
    UnknownCordisEventError,
    all_execution_points,
    lookup_cordis_name,
)
from lca.contracts.observability.event_descriptor import EventDescriptor
from lca.contracts.observability.loop_cursor import PhaseName


def test_event_descriptor_is_frozen() -> None:
    """EventDescriptor 必须 frozen=True;字段赋值冻结。"""
    descriptor = EventDescriptor.derive("writable.step.start")
    with pytest.raises(FrozenInstanceError):
        descriptor.execution_point = "writable.step.end"  # type: ignore[misc]


def test_derive_phase_think_fold_yields_cordis_name() -> None:
    """``phase.think.fold`` 必须派生到 ``agent.phase.think.fold``。"""
    descriptor = EventDescriptor.derive("phase.think.fold")
    assert descriptor.execution_point == "phase.think.fold"
    assert descriptor.cordis_name == "agent.phase.think.fold"
    assert descriptor.schema_version >= 1
    assert descriptor.ignorable is False


def test_all_seven_phase_names_have_cordis_derivation() -> None:
    """全部 7 个 PhaseName 字面值必须在 cordis_event_table 登记。"""
    expected_ep_for_phase = {phase: f"phase.{phase}.fold" for phase in PhaseName.__args__}
    for phase, ep in expected_ep_for_phase.items():
        descriptor = EventDescriptor.derive(ep)
        assert descriptor.cordis_name == f"agent.{ep}", f"phase={phase!r} 派生 cordis_name 不匹配"


def test_unknown_execution_point_raises_unknown_event() -> None:
    """未登记 EP 必须抛 ``UnknownCordisEventError``(L15 UnknownEventType 子型)。"""
    with pytest.raises(UnknownCordisEventError):
        EventDescriptor.derive("agent.bogus.event.does_not_exist")
    # 必须也是 KeyError 子类(L15 方向感知兜底)
    with pytest.raises(KeyError):
        EventDescriptor.derive("phase.unknown.fold")


def test_schema_version_present_for_every_registered_ep() -> None:
    """每个登记 EP 的 EventDescriptor 都携带 ``schema_version >= 1``(L15)。"""
    for ep in all_execution_points():
        descriptor = EventDescriptor.derive(ep)
        assert descriptor.schema_version >= 1, f"EP={ep!r} schema_version 必须 >= 1"


def test_derive_is_deterministic() -> None:
    """同一 EP 多次派生得到字面相同的 EventDescriptor;无副作用。"""
    a = EventDescriptor.derive("writable.iteration.close")
    b = EventDescriptor.derive("writable.iteration.close")
    assert a == b
    assert a.cordis_name == b.cordis_name == "agent.writable.iteration.close"


def test_lookup_helper_returns_table_entry() -> None:
    """``lookup_cordis_name`` 直查表与 EventDescriptor.derive 字段一致。"""
    entry: CordisEventTableEntry = lookup_cordis_name("step.thinking.record")
    descriptor = EventDescriptor.derive("step.thinking.record")
    assert entry.cordis_name == descriptor.cordis_name
    assert entry.schema_version == descriptor.schema_version
    assert entry.ignorable == descriptor.ignorable
