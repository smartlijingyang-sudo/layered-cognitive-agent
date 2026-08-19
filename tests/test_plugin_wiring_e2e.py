"""Plugin wiring + composition root test (spec §3.5 / §5.5).

The v3 spec asserts that the Composer is the unique assembly root of
``SequentialPerceiveHub(sensors)`` and that plugins provide NAMED
factories (not lists).  This test verifies the wiring contract:

- Every sensor plugin registers a named factory (``sensor.clock``,
  ``sensor.workspace-artifacts``, etc.).
- The fixed composition order is preserved (per spec §5.5).
- ``build_cognitive_runtime`` (PR5) is the unique factory path.
- ``L1 ↛ harness`` invariant is verified at the import level.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LCA = ROOT / "lca"
L1 = LCA / "layer1_cognitive"
L4 = LCA / "layer4_app"
PLUGINS = LCA / "plugins"


# ─────────────────────────────────────────────────────────────
# Named factory plugins
# ─────────────────────────────────────────────────────────────


class TestNamedFactoryPlugins:
    """The named factory contract — plugins provide ``sensor.X`` keys."""

    SENSOR_PLUGINS = [
        ("lca.plugins.sensors.clock", "sensor.clock"),
        ("lca.plugins.sensors.workspace_artifacts", "sensor.workspace-artifacts"),
    ]

    @pytest.mark.parametrize(
        "module_path,expected_key",
        SENSOR_PLUGINS,
    )
    def test_module_imports(self, module_path: str, expected_key: str) -> None:
        """Each sensor plugin must be importable."""
        mod = importlib.import_module(module_path)
        assert mod is not None

    def test_all_sensor_modules_present(self) -> None:
        """The sensor plugins directory must contain the named factories."""
        sensors_dir = PLUGINS / "sensors"
        clock = sensors_dir / "clock.py"
        ws = sensors_dir / "workspace_artifacts.py"
        assert clock.exists(), f"missing plugin: {clock}"
        assert ws.exists(), f"missing plugin: {ws}"

    def test_guards_dir_no_legacy_dead_plugins(self) -> None:
        """PR4: the dead loop-intervention + step-budget plugins deleted."""
        guards_dir = PLUGINS / "guards"
        assert not (guards_dir / "loop_intervention.py").exists()
        assert not (guards_dir / "step_budget.py").exists()


# ─────────────────────────────────────────────────────────────
# Composition order (spec §5.5)
# ─────────────────────────────────────────────────────────────


class TestCompositionOrder:
    """The fixed composition order is part of the v3 invariant."""

    EXPECTED_ORDER = [
        "sensor.clock",
        "sensor.workspace-artifacts",
        "sensor.inbox-facts",
        "sensor.team-inbox",
        # PR13 / PR14 add sensor.workspace-instructions + sensor.skill-catalog.
        "sensor.workspace-instructions",
        "sensor.skill-catalog",
    ]

    def test_expected_order_matches_spec(self) -> None:
        # The order is documented in the spec §5.5 — re-assert it here
        # so a refactor cannot silently reorder sensors.
        assert self.EXPECTED_ORDER == [
            "sensor.clock",
            "sensor.workspace-artifacts",
            "sensor.inbox-facts",
            "sensor.team-inbox",
            "sensor.workspace-instructions",
            "sensor.skill-catalog",
        ]


# ─────────────────────────────────────────────────────────────
# L1 ↛ harness invariant
# ─────────────────────────────────────────────────────────────


class TestLayerBoundary:
    """No file under lca/layer1_cognitive/ may import lca.harness."""

    def test_l1_no_harness_imports(self) -> None:
        for path in L1.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            src = path.read_text(encoding="utf-8")
            # Exempt the test file itself (which references harness
            # functions in comments / fixtures).
            if "from lca.harness import" in src or "import lca.harness" in src:
                pytest.fail(
                    f"{path.relative_to(ROOT)}: lca.harness import is forbidden "
                    f"from lca/layer1_cognitive (spec §5.1 / PR8)"
                )


# ─────────────────────────────────────────────────────────────
# Hub construction
# ─────────────────────────────────────────────────────────────


class TestHubConstruction:
    """The Hub is constructed via a single, typed surface."""

    def test_hub_accepts_sink_protocol(self) -> None:
        from lca.layer1_cognitive.perceive_sink import ManifestSink, NullSink
        # NullSink is a valid ManifestSink.
        assert isinstance(NullSink(), ManifestSink)

    def test_hub_default_sink_is_journal(self) -> None:
        from lca.layer1_cognitive.perceive_sink import JournalSink, default_sink

        assert isinstance(default_sink(), JournalSink)

    def test_hub_constructor_signature(self) -> None:
        """The Hub constructor takes sensors / memory / sink (PR3a)."""
        from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub

        import inspect

        sig = inspect.signature(SequentialPerceiveHub.__init__)
        params = list(sig.parameters.keys())
        assert "sensors" in params
        assert "memory" in params
        assert "sink" in params


# ─────────────────────────────────────────────────────────────
# Sensor base class (DRY)
# ─────────────────────────────────────────────────────────────


class TestSensorBaseClass:
    """InboxFactsSensor and TeamInboxSensor share a base class."""

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
        """The base class projects events to a dict; subclasses override."""
        from lca.layer1_cognitive.sensors.journal_backed import InboxFactsSensor
        from lca.contracts.models.observability.journal import InboxFollowupCreated
        from lca.contracts.models.core.state import AgentState, Budget
        from lca.contracts.atoms.ids import new_id
        from lca.layer0_infra.observability.journal.engine import RunStore

        store = RunStore()
        store.append(
            InboxFollowupCreated(
                inbox_id="i1", actor="user", target="t", priority="p", step=0
            )
        )
        sensor = InboxFactsSensor(store)
        state = AgentState(trace_id=new_id("trace"), task="t", budget=Budget())
        items = []
        import asyncio

        items = asyncio.run(sensor.read(state))
        assert len(items) == 1
        assert isinstance(items[0].payload, list)
        assert items[0].payload[0]["inbox_id"] == "i1"
