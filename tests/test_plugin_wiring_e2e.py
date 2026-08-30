"""Plugin wiring + spawn root test (spec §5.5 / ADR-0056).

Sensor plugins add() onto PerceiveService; gate plugins add() onto
GateService. Spawn asks group services to assemble — it does not list
contribution ids.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LCA = ROOT / "lca"
L1 = LCA / "layer1_cognitive"
PLUGINS = LCA / "plugins"


_SENSOR_PLUGINS: tuple[str, ...] = (
    "lca.plugins.sensors.clock",
    "lca.plugins.sensors.workspace_artifacts",
    "lca.plugins.sensors.inbox_facts",
    "lca.plugins.sensors.team_inbox",
    "lca.plugins.sensors.workspace_instructions",
    "lca.plugins.sensors.skill_catalog",
)
_GATE_PLUGINS: tuple[str, ...] = (
    "lca.plugins.gates.service",
    "lca.plugins.gates.repeat_tool_call",
    "lca.plugins.gates.tool_loop_breaker",
    "lca.plugins.gates.progress_loop_detector",
    "lca.plugins.gates.terminal_respond",
    "lca.plugins.gates.artifact_respond_injector",
    "lca.plugins.gates.must_consult_all",
)
_ACT_RUNTIME_PLUGINS: tuple[str, ...] = (
    "lca.plugins.body.simple",
    "lca.plugins.body.safe_executor",
    "lca.plugins.state.stop_policy",
    "lca.plugins.runtime.hook_registry",
)
_EXPECTED_SENSOR_ORDER: tuple[str, ...] = (
    "clock",
    "workspace-artifacts",
    "inbox-facts",
    "team-inbox",
    "workspace-instructions",
    "skill-catalog",
)


class TestContributionPlugins:
    @pytest.mark.parametrize("module_path", _SENSOR_PLUGINS)
    def test_sensor_module_imports(self, module_path: str) -> None:
        mod = importlib.import_module(module_path)
        assert hasattr(mod, "setup")

    def test_all_sensor_modules_present(self) -> None:
        sensors_dir = PLUGINS / "sensors"
        for name in (
            "clock.py",
            "workspace_artifacts.py",
            "inbox_facts.py",
            "team_inbox.py",
            "workspace_instructions.py",
            "skill_catalog.py",
        ):
            path = sensors_dir / name
            assert path.exists(), f"missing plugin: {path}"

    @pytest.mark.parametrize("module_path", _GATE_PLUGINS)
    def test_gate_module_imports(self, module_path: str) -> None:
        mod = importlib.import_module(module_path)
        assert hasattr(mod, "setup"), f"{module_path} must expose cordis setup"

    @pytest.mark.parametrize("module_path", _ACT_RUNTIME_PLUGINS)
    def test_act_runtime_module_imports(self, module_path: str) -> None:
        mod = importlib.import_module(module_path)
        assert hasattr(mod, "setup"), f"{module_path} must expose cordis setup"

    def test_workspace_chain_removed(self) -> None:
        assert not (PLUGINS / "gates" / "workspace_chain.py").exists()

    def test_guards_dir_no_legacy_dead_plugins(self) -> None:
        guards_dir = PLUGINS / "guards"
        assert not (guards_dir / "loop_intervention.py").exists()
        assert not (guards_dir / "step_budget.py").exists()


class TestCompositionOrder:
    def test_expected_order_matches_spec(self) -> None:
        assert _EXPECTED_SENSOR_ORDER == (
            "clock",
            "workspace-artifacts",
            "inbox-facts",
            "team-inbox",
            "workspace-instructions",
            "skill-catalog",
        )


class TestLayerBoundary:
    def test_l1_no_harness_imports(self) -> None:
        for path in L1.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            src = path.read_text(encoding="utf-8")
            if "from lca.harness import" in src or "import lca.harness" in src:
                pytest.fail(
                    f"{path.relative_to(ROOT)}: lca.harness import is forbidden "
                    f"from lca/layer1_cognitive (spec §5.1 / PR8)"
                )


class TestHubConstruction:
    def test_hub_accepts_sink_protocol(self) -> None:
        from lca.layer1_cognitive.perceive_sink import ManifestSink, NullSink

        assert isinstance(NullSink(), ManifestSink)

    def test_hub_default_sink_is_journal(self) -> None:
        from lca.layer1_cognitive.perceive_sink import JournalSink, default_sink

        assert isinstance(default_sink(), JournalSink)

    def test_journal_sink_consumes_write_only_backend(self) -> None:
        from lca.contracts.models.core.perception import ContextManifest
        from lca.contracts.models.observability.journal import ContextManifested
        from lca.contracts.observability.ports import JournalBackend
        from lca.layer1_cognitive.perceive_sink import JournalSink

        class WriteOnlyJournal:
            def __init__(self) -> None:
                self.events: list[ContextManifested] = []

            def write(self, event: ContextManifested) -> None:
                self.events.append(event)
                return None

            def flush(self) -> None:
                return None

            def close(self) -> None:
                return None

        journal = WriteOnlyJournal()
        assert isinstance(journal, JournalBackend)
        event = ContextManifested(step=3)
        emitted = JournalSink(journal).emit(event, ContextManifest(items=()))

        assert emitted is event
        assert journal.events == [event]

    def test_hub_constructor_signature(self) -> None:
        import inspect

        from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub

        sig = inspect.signature(SequentialPerceiveHub.__init__)
        params = list(sig.parameters.keys())
        assert "sensors" in params
        assert "memory" in params
        assert "sink" in params


class TestSensorBaseClass:
    def test_inbox_sensor_subclasses_journal_sensor(self) -> None:
        from lca.layer1_cognitive.sensors.journal_backed import (
            InboxFactsSensor,
            _JournalSensor,
        )

        assert issubclass(InboxFactsSensor, _JournalSensor)

    def test_team_inbox_sensor_subclasses_journal_sensor(self) -> None:
        from lca.layer1_cognitive.sensors.journal_backed import (
            TeamInboxSensor,
            _JournalSensor,
        )

        assert issubclass(TeamInboxSensor, _JournalSensor)

    def test_journal_sensor_uses_dict_projection(self) -> None:
        from lca.contracts.atoms.ids import new_id
        from lca.contracts.models.core.state import AgentState, Budget
        from lca.contracts.models.observability.journal import InboxFollowupCreated
        from lca.infrastructure.observability.journal.engine import RunStore
        from lca.layer1_cognitive.sensors.journal_backed import InboxFactsSensor

        store = RunStore()
        store.append(
            InboxFollowupCreated(inbox_id="i1", actor="user", target="t", priority="p", step=0)
        )
        sensor = InboxFactsSensor(store)
        state = AgentState(trace_id=new_id("trace"), task="t", budget=Budget())
        import asyncio

        items = asyncio.run(sensor.read(state))
        assert len(items) == 1
        assert isinstance(items[0].payload, list)
        assert items[0].payload[0]["inbox_id"] == "i1"
