"""Boot typed JournalEvent 注册完整性测试（ADR-0116 PR-3）。

覆盖:
- 3 个 event 是 frozen dataclass + slots=True
- BootPluginFiberSpawned.stage 强引用 lca_kernel.stages.Stage(IntEnum)
  - stage=Stage.RESOLVE 通过
  - stage="not a stage" 抛 TypeError
  - stage=Stage(99) 抛 ValueError
- JOURNAL_EVENT_CLASSES 包含 3 个 entry
- event_descriptors_data.build_default_registry() 返回的 registry 包含 3 个 entry
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import IntEnum

import pytest

from lca.contracts.models.observability.journal import (
    BootObservabilityAssembled,
    BootPluginFiberSpawned,
    BootProfileResolved,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.infrastructure.observability.events.event_descriptors_data import (
    build_default_registry,
)
from lca_kernel.stages import Stage

_BOOT_EVENT_NAMES = frozenset(
    {"BootProfileResolved", "BootPluginFiberSpawned", "BootObservabilityAssembled"}
)


def _is_frozen_slots_dataclass(cls: type) -> bool:
    """frozen=True + slots=True 的 dataclass 必须满足 ``__slots__`` 已设置
    且 ``frozen=True`` 体现在 ``cls.__dataclass_params__.frozen``。"""
    if not is_dataclass(cls):
        return False
    params = getattr(cls, "__dataclass_params__", None)
    if params is None or not getattr(params, "frozen", False):
        return False
    return bool(getattr(cls, "__slots__", ()))


class TestBootEventShapes:
    """三个 boot event 必须是 frozen slots=True dataclass,继承 JournalEvent。"""

    @pytest.mark.parametrize(
        "cls",
        [BootProfileResolved, BootPluginFiberSpawned, BootObservabilityAssembled],
    )
    def test_event_is_frozen_slots_dataclass(self, cls: type) -> None:
        assert _is_frozen_slots_dataclass(cls), f"{cls.__name__} 必须 frozen=True + slots=True"

    @pytest.mark.parametrize(
        "cls",
        [BootProfileResolved, BootPluginFiberSpawned, BootObservabilityAssembled],
    )
    def test_event_inherits_journal_event(self, cls: type) -> None:
        from lca.contracts.models.observability.journal import JournalEvent

        assert issubclass(cls, JournalEvent), f"{cls.__name__} 必须继承 JournalEvent"


class TestBootProfileResolvedPayload:
    """BootProfileResolved payload 形状 (ADR-0116 决定 4)。"""

    def test_required_fields_present(self) -> None:
        names = {f.name for f in fields(BootProfileResolved)}
        assert {
            "profile_path",
            "manifest_hash",
            "plugin_count",
            "bundle_count",
            "duration_ms",
            "topo_order",
        } <= names

    def test_default_construction_yields_type(self) -> None:
        instance = BootProfileResolved()
        assert type(instance).__name__ == "BootProfileResolved"


class TestBootObservabilityAssembledPayload:
    """BootObservabilityAssembled payload 形状 (ADR-0116 决定 6)。"""

    def test_required_fields_present(self) -> None:
        names = {f.name for f in fields(BootObservabilityAssembled)}
        assert {"bound_seams", "evidence_store_kind", "journal_enabled", "duration_ms"} <= names

    def test_default_construction_yields_type(self) -> None:
        instance = BootObservabilityAssembled()
        assert type(instance).__name__ == "BootObservabilityAssembled"


class TestBootPluginFiberSpawnedPayload:
    """BootPluginFiberSpawned payload + stage 强类型 (ADR-0116 决定 5)。"""

    def test_required_fields_present(self) -> None:
        names = {f.name for f in fields(BootPluginFiberSpawned)}
        assert {
            "plugin_id",
            "layer",
            "kind",
            "stage",
            "duration_ms",
            "status",
            "failure_kind",
            "failure_message",
        } <= names

    def test_default_construction_yields_type(self) -> None:
        """sentinel 默认构造走测试兼容性路径,不抛。"""
        instance = BootPluginFiberSpawned()
        assert type(instance).__name__ == "BootPluginFiberSpawned"

    def test_stage_with_resolve_passes(self) -> None:
        """stage=Stage.RESOLVE 应合法构造。"""
        event = BootPluginFiberSpawned(
            plugin_id="plugin_x",
            layer="L2",
            kind="provider",
            stage=Stage.RESOLVE,
            duration_ms=1.5,
            status="ok",
        )
        assert event.stage is Stage.RESOLVE
        assert event.plugin_id == "plugin_x"
        assert event.status == "ok"

    def test_stage_with_bootstrap_all_six_passes(self) -> None:
        """Stage 1-6 全值范围均通过守卫。"""
        for stage_value in (
            Stage.SOURCE,
            Stage.RESOLVE,
            Stage.TOPO,
            Stage.PLAN,
            Stage.BOOT,
            Stage.OBSERVABILITY,
        ):
            event = BootPluginFiberSpawned(
                plugin_id="plugin_x",
                layer="L2",
                kind="provider",
                stage=stage_value,
                duration_ms=1.0,
                status="started",
            )
            assert event.stage is stage_value

    def test_stage_string_raises_typeerror(self) -> None:
        """stage="not a stage" → TypeError (非 Stage 枚举)。"""
        with pytest.raises(TypeError, match=r"stage must be Stage enum"):
            BootPluginFiberSpawned(
                plugin_id="plugin_x",
                layer="L2",
                kind="provider",
                stage="not a stage",  # type: ignore[arg-type]
                duration_ms=1.0,
                status="ok",
            )

    def test_stage_out_of_range_raises_valueerror(self) -> None:
        """stage=Stage(99) → ValueError (值域 [1, 6] 外)。

        IntEnum 在构造越界值时本身抛 ValueError;Stage 不可构造 0/7/99。
        """
        with pytest.raises(ValueError):
            BootPluginFiberSpawned(
                plugin_id="plugin_x",
                layer="L2",
                kind="provider",
                stage=Stage(99),
                duration_ms=1.0,
                status="ok",
            )

    def test_stage_zero_raises_valueerror(self) -> None:
        """stage=Stage(0) → ValueError (IntEnum 拒绝 0,值域起点是 1)。"""
        with pytest.raises(ValueError):
            BootPluginFiberSpawned(
                plugin_id="plugin_x",
                layer="L2",
                kind="provider",
                stage=Stage(0),
                duration_ms=1.0,
                status="ok",
            )


class TestJournalCatalogBootEvents:
    """JOURNAL_EVENT_CLASSES 必须包含三个 boot entry。"""

    def test_journal_event_classes_contains_boot_entries(self) -> None:
        assert set(JOURNAL_EVENT_CLASSES) >= _BOOT_EVENT_NAMES, (
            f"JOURNAL_EVENT_CLASSES 缺少 boot entries: "
            f"{_BOOT_EVENT_NAMES - set(JOURNAL_EVENT_CLASSES)}"
        )

    def test_journal_event_classes_boot_payload_bindings(self) -> None:
        assert JOURNAL_EVENT_CLASSES["BootProfileResolved"] is BootProfileResolved
        assert JOURNAL_EVENT_CLASSES["BootPluginFiberSpawned"] is BootPluginFiberSpawned
        assert JOURNAL_EVENT_CLASSES["BootObservabilityAssembled"] is BootObservabilityAssembled


class TestEventDescriptorsBootEvents:
    """build_default_registry() 必须包含三个 boot EventDescriptor。"""

    def test_registry_contains_boot_entries(self) -> None:
        registry = build_default_registry()
        names = set(registry.all_type_names())
        assert names >= _BOOT_EVENT_NAMES, (
            f"build_default_registry() 缺少 boot entries: {_BOOT_EVENT_NAMES - names}"
        )

    def test_registry_boot_descriptors_have_correct_metadata(self) -> None:
        registry = build_default_registry()
        descriptor = registry.require("BootProfileResolved")
        assert descriptor.emitter == "lca_kernel.source_resolve"
        assert descriptor.payload_class is BootProfileResolved

        descriptor = registry.require("BootPluginFiberSpawned")
        assert descriptor.emitter == "lca_kernel.boot"
        assert descriptor.payload_class is BootPluginFiberSpawned

        descriptor = registry.require("BootObservabilityAssembled")
        assert descriptor.emitter == "lca_kernel.observability"
        assert descriptor.payload_class is BootObservabilityAssembled


class TestStageIntEnumIsSsot:
    """Stage(IntEnum) 是 BootPluginFiberSpawned.stage 唯一合法来源。"""

    def test_stage_is_intenum(self) -> None:
        assert issubclass(Stage, IntEnum), "Stage 必须是 IntEnum"

    def test_stage_values_one_through_six(self) -> None:
        assert [int(s) for s in Stage] == [1, 2, 3, 4, 5, 6]
