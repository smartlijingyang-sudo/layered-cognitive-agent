from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.protocols.cognition import DecisionGateAssembler, PerceiveHubAssembler
from lca.layer1_cognitive.gate_service import GateService
from lca.layer1_cognitive.perceive_service import PerceiveService


@dataclass
class _Sensor:
    name: str

    async def read(self, state: object) -> list[object]:
        return []


@dataclass
class _RecordingHub:
    sensors: tuple[_Sensor, ...]
    memory: object

    async def perceive(self, state: object) -> ContextManifest:
        return ContextManifest(items=())


class _RecordingHubAssembler(PerceiveHubAssembler):
    def assemble(self, *, sensors, memory):
        return _RecordingHub(tuple(sensors), memory)


@dataclass
class _PassthroughGate:
    name: str

    async def enforce(self, state: object, decision: Decision) -> Decision:
        return decision


@dataclass
class _RecordingGate:
    gates: tuple[_PassthroughGate, ...]

    async def enforce(self, state: object, decision: Decision) -> Decision:
        return decision


class _RecordingGateAssembler(DecisionGateAssembler):
    def assemble(self, *, gates):
        return _RecordingGate(tuple(gates))


class TestPerceiveGroupAssembly:
    def test_assembler_is_a_required_profile_contribution(self) -> None:
        service = PerceiveService()

        with pytest.raises(MissingCapabilityError, match="no Hub assembler"):
            service.assemble(memory=object())

    def test_selected_assembler_receives_ordered_sensor_contributions(self) -> None:
        service = PerceiveService()
        service.add(lambda: _Sensor("late"), id="late", order=20)
        service.add(lambda: _Sensor("early"), id="early", order=10)
        service.set_assembler(_RecordingHubAssembler(), id="recording")

        memory = object()
        hub = service.assemble(memory=memory)

        assert isinstance(hub, _RecordingHub)
        assert hub.memory is memory
        assert [sensor.name for sensor in hub.sensors] == ["early", "late"]
        assert service.assembler_id == "recording"

    def test_conflicting_assemblers_fail_during_boot_registration(self) -> None:
        service = PerceiveService()
        service.set_assembler(_RecordingHubAssembler(), id="one")

        with pytest.raises(ValueError, match="already has assembler"):
            service.set_assembler(_RecordingHubAssembler(), id="two")

    def test_duplicate_sensor_contribution_fails_closed(self) -> None:
        service = PerceiveService()
        service.add(lambda: _Sensor("first"), id="same", order=10)

        with pytest.raises(ValueError, match="already has sensor contribution 'same'"):
            service.add(lambda: _Sensor("second"), id="same", order=20)


class TestGateGroupAssembly:
    def test_assembler_is_a_required_profile_contribution(self) -> None:
        service = GateService()

        with pytest.raises(MissingCapabilityError, match="no assembler"):
            service.assemble()

    def test_selected_assembler_receives_ordered_slot_contributions(self) -> None:
        service = GateService()
        service.add(lambda: _PassthroughGate("late"), id="late", order=20)
        service.add(lambda: _PassthroughGate("early"), id="early", order=10)
        service.add(lambda: _PassthroughGate("other"), id="other", slot="lead", order=0)
        service.set_assembler(_RecordingGateAssembler(), id="recording")

        gate = service.assemble()

        assert isinstance(gate, _RecordingGate)
        assert [item.name for item in gate.gates] == ["early", "late"]
        assert service.assembler_id == "recording"

    def test_conflicting_assemblers_fail_during_boot_registration(self) -> None:
        service = GateService()
        service.set_assembler(_RecordingGateAssembler(), id="one")

        with pytest.raises(ValueError, match="already has assembler"):
            service.set_assembler(_RecordingGateAssembler(), id="two")

    def test_duplicate_gate_contribution_fails_closed(self) -> None:
        service = GateService()
        service.add(lambda: _PassthroughGate("first"), id="same", order=10)

        with pytest.raises(ValueError, match="already has gate contribution 'same'"):
            service.add(lambda: _PassthroughGate("second"), id="same", order=20)


class TestCognitiveGroupPluginWiring:
    @pytest.mark.asyncio
    async def test_default_profile_selects_both_group_assemblers(self) -> None:
        from lca.layer4_app.api import ensure_default_ctx

        scope = await ensure_default_ctx()

        assert scope.inject("perceive").assembler_id == "sequential"
        assert scope.inject("gates").assembler_id == "sequential"

    def test_group_services_do_not_name_standard_implementations(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        perceive_source = (root / "lca/layer1_cognitive/perceive_service.py").read_text(
            encoding="utf-8"
        )
        gate_source = (root / "lca/layer1_cognitive/gate_service.py").read_text(encoding="utf-8")

        assert "SequentialPerceiveHub" not in perceive_source
        assert "ChainedDecisionGate" not in gate_source
        assert "register_builtin_sensors" not in perceive_source

    def test_standard_bundles_declare_group_assembly_plugins(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        for name in ("web-app.yaml", "scenario-standard.yaml"):
            content = (root / "bundles" / name).read_text(encoding="utf-8")
            assert "lca.plugins.perceive.sequential_hub" in content
            assert "lca.plugins.gates.chained" in content
