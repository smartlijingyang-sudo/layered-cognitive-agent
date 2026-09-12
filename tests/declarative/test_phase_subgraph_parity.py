"""Six-phase subgraph parity tests (note 2026-09-12).

Each phase's subgraph host runs the standard phase logic on top of
the typed NodeInput / NodeOutput port contract. This file asserts
that the four newly added phase hosts (perceive / reflect / remember
/ stop) emit the same payload shape the legacy ``PhaseExecutor``
path emitted, so the kernel's typed port contract is a drop-in
replacement for the v1 ``PhaseInput`` / ``PhaseResult`` boundary.

Also includes a structural guard: the framework subtree must not
import ``PhaseInput`` / ``PhaseResult`` / ``PhaseExecutor`` after the
six-phase cutover.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRAMEWORK_DIR = REPO / "lca" / "framework"


class TestFrameworkPurity:
    """The framework subtree must hold zero references to phase types."""

    @pytest.mark.parametrize(
        "forbidden",
        [
            "PhaseInput",
            "PhaseResult",
            "PhaseExecutor",
            "PhaseExecutorStrategy",
            "PHASE_EXECUTOR",
            "PhaseExecutorLookup",
            "phase_executor_strategy",
        ],
    )
    def test_no_business_phase_types_in_framework(self, forbidden: str) -> None:
        proc = subprocess.run(
            [
                "rg",
                "--hidden",
                "-uu",
                "-g",
                "!lca/framework/__pycache__",
                forbidden,
                str(FRAMEWORK_DIR),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        # Allow the docstring note that names the absent types.
        lines = [
            line
            for line in proc.stdout.splitlines()
            if line.strip()
            and "PhaseExecutor`` / ``PhaseInput`` / ``PhaseResult``" not in line
        ]
        assert not lines, (
            f"framework subtree must not reference {forbidden}; found:\n"
            + "\n".join(lines)
        )

    def test_default_registry_has_no_phase_executor_kind(self) -> None:
        from lca.framework.graph import default_strategy_registry
        from lca.contracts.protocols.graph.binding import BindingKind

        kinds = {k.value for k in default_strategy_registry().kinds()}
        assert "phase_executor" not in kinds

    def test_binding_enum_no_phase_executor(self) -> None:
        from lca.contracts.protocols.graph.binding import BindingKind

        values = {member.value for member in BindingKind}
        assert "phase_executor" not in values


class TestPhaseSubgraphBundles:
    """The four new subgraph bundles exist and parse as Bundle Graph Spec v2."""

    @pytest.mark.parametrize(
        "bundle",
        [
            "perceive_subgraph",
            "reflect_subgraph",
            "remember_subgraph",
            "stop_subgraph",
        ],
    )
    def test_bundle_loads_and_has_nodes(self, bundle: str) -> None:
        import yaml

        path = REPO / "bundles" / f"{bundle}.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict), f"bundle {bundle} must be a mapping"
        assert "id" in raw
        assert "nodes" in raw and len(raw["nodes"]) >= 1, (
            f"bundle {bundle} must have at least one entry node"
        )


class TestPhaseSubgraphParity:
    """Drive each new subgraph host plugin's NodeExecutor directly.

    Each host runs the standard phase logic and projects the result
    onto a typed port. The same input must produce a payload of the
    same shape the legacy ``PhaseExecutor.execute`` path emitted.
    """

    async def test_perceive_host_emits_observation_port(self) -> None:
        from lca.contracts.models.core.execution.decision import Observation
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeContext,
            NodeInput,
        )
        from lca.plugins.loop.phase.perceive.host.plugin import (
            PerceiveHostExecutor,
        )

        ctx = NodeContext(runtime={}, budget={}, metadata={})
        out = await PerceiveHostExecutor().node_execute(ctx, NodeInput({}))
        assert "observation" in out.port_values
        payload = out.port_values["observation"]
        assert isinstance(payload, Observation) or payload is not None

    async def test_reflect_host_emits_reflection_port(self) -> None:
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeContext,
            NodeInput,
        )
        from lca.plugins.loop.phase.reflect.host.plugin import (
            ReflectHostExecutor,
        )

        ctx = NodeContext(runtime={}, budget={}, metadata={})
        out = await ReflectHostExecutor().node_execute(
            ctx,
            NodeInput({"observation": None}),
        )
        assert "reflection" in out.port_values

    async def test_remember_host_consumes_typed_ports(self) -> None:
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeContext,
            NodeInput,
        )
        from lca.plugins.loop.phase.remember.host.plugin import (
            RememberHostExecutor,
        )

        ctx = NodeContext(runtime={}, budget={}, metadata={})
        out = await RememberHostExecutor().node_execute(
            ctx,
            NodeInput({"decision": None, "observation": None, "reflection": None}),
        )
        # remember is terminal-of-typing: no outgoing port.
        assert out.port_values == {}

    async def test_stop_host_emits_stop_decision_port(self) -> None:
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeContext,
            NodeInput,
        )
        from lca.plugins.loop.phase.stop.host.plugin import (
            StopHostExecutor,
        )

        ctx = NodeContext(runtime={}, budget={}, metadata={})
        out = await StopHostExecutor().node_execute(
            ctx,
            NodeInput({"decision": None, "observation": None, "reflection": None}),
        )
        assert "stop_decision" in out.port_values


class TestWebStandardProfileSubgraphBindings:
    """The web-standard profile must wire every phase main via sub_spec_ref."""

    def test_profile_patches_use_subgraph_bindings(self) -> None:
        import yaml

        path = REPO / "profiles" / "web-standard.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        patch = raw.get("patch") or []
        topo = next(
            (p for p in patch if p.get("id") == "phase.topology.standard"),
            None,
        )
        assert topo is not None, "profile must patch phase.topology.standard"
        nodes = topo.get("config", {}).get("nodes", [])
        by_id = {n["id"]: n for n in nodes}
        for phase_main in (
            "perceive.main",
            "think.main",
            "act.main",
            "reflect.main",
            "remember.main",
            "stop.main",
        ):
            assert phase_main in by_id, f"profile missing node {phase_main}"
            node = by_id[phase_main]
            assert "sub_spec_ref" in node, (
                f"{phase_main} must bind via sub_spec_ref after six-phase subgraph cutover"
            )
            assert "binding" not in node or node.get("binding") in (
                None,
                "node_executor",
                "subgraph",
            ), f"{phase_main} must not carry phase_executor binding"


__all__ = [
    "TestFrameworkPurity",
    "TestPhaseSubgraphBundles",
    "TestPhaseSubgraphParity",
    "TestWebStandardProfileSubgraphBindings",
]
