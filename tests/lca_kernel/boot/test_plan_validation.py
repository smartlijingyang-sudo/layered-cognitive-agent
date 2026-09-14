"""Boot-time plan validation — fail-loud gate for malformed plans.

The kernel must refuse to start when any profile plan has malformed
ports / predicates / fields. This complements ``lift_graph_spec``'s
in-process validation by walking every plan in a resolved profile and
aggregating all errors before raising.

The tests below exercise :func:`validate_profile_plans` against
``ResolvedProfile``-shaped inputs. Each malformed plan triggers a
:class:`PlanLiftError` carrying structured context (``plan_id``,
``port_name``) so debug never relies on log search.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.harness.profile.resolve.resolve import ResolvedProfile
from lca_kernel.boot.plan_validation import validate_profile_plans

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_bundle(tmp_path: Path, name: str, mapping: dict[str, Any]) -> str:
    """Write a YAML bundle and return its absolute path."""
    path = tmp_path / name
    path.write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")
    return str(path)


def _resolved_profile(bundle_paths: tuple[str, ...]) -> ResolvedProfile:
    """Build a minimal :class:`ResolvedProfile` carrying only ``bundles``."""
    return ResolvedProfile(
        profile_path="<test>",
        bundles=bundle_paths,
        plugins=(),
        dag_edges=(),
        manifest_hash="0" * 64,
        env_refs=(),
    )


# Minimal valid plan: two nodes, terminal True on the second, no predicates.
_VALID_PLAN: dict[str, Any] = {
    "id": "valid.outer",
    "nodes": [
        {
            "id": "a",
            "binding": "node_executor",
            "outputs": ["decision"],
            "entry": True,
        },
        {
            "id": "b",
            "binding": "node_executor",
            "inputs": ["decision"],
            "terminal": True,
        },
    ],
    "edges": [
        {"from": "a", "to": "b", "when": True},
    ],
}


# Malformed: legacy string ``when:`` DSL (no longer supported).
_STRING_PREDICATE_PLAN: dict[str, Any] = {
    "id": "broken.string_predicate",
    "nodes": [
        {
            "id": "a",
            "binding": "node_executor",
            "outputs": ["decision"],
            "entry": True,
        },
        {
            "id": "b",
            "binding": "node_executor",
            "inputs": ["decision"],
            "terminal": True,
        },
    ],
    "edges": [
        {
            "from": "a",
            "to": "b",
            "when": 'result.payload.decision.action_type == "use_tool"',
        },
    ],
}


# Malformed: typed predicate references a port not in source outputs.
_UNKNOWN_PORT_PLAN: dict[str, Any] = {
    "id": "broken.unknown_port",
    "nodes": [
        {
            "id": "a",
            "binding": "node_executor",
            "outputs": ["decision"],
            "entry": True,
        },
        {
            "id": "b",
            "binding": "node_executor",
            "inputs": ["decision"],
            "terminal": True,
        },
    ],
    "edges": [
        {
            "from": "a",
            "to": "b",
            "when": {"kind": "eq", "port": {"name": "nonexistent"}, "value": "x"},
        },
    ],
}


# Malformed: no terminal node and no terminal_predicate.
_NO_TERMINATION_PLAN: dict[str, Any] = {
    "id": "broken.no_termination",
    "nodes": [
        {
            "id": "a",
            "binding": "node_executor",
            "outputs": ["x"],
            "entry": True,
        },
        {
            "id": "b",
            "binding": "node_executor",
            "inputs": ["x"],
            "outputs": ["y"],
        },
    ],
    "edges": [
        {"from": "a", "to": "b", "when": True},
    ],
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestValidateProfilePlans:
    def test_valid_profile_passes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A profile whose every plan lifts clean passes validation."""
        bundle = _write_bundle(tmp_path, "phase_main_outer.yaml", _VALID_PLAN)
        resolved = _resolved_profile((bundle,))

        validate_profile_plans(resolved)  # must not raise

        captured = capsys.readouterr()
        # stderr should announce the validation result so it shows in
        # /tmp/lca-kernel.log per the boot contract.
        assert "1 plans validated" in captured.err

    # ---------------------------------------------------------------------------
    # String ``when:`` DSL — the silent-None bug class.
    # ---------------------------------------------------------------------------

    def test_malformed_predicate_raises_at_boot(self, tmp_path: Path) -> None:
        """String ``when:`` is rejected at boot, not at first run.

        The top-level error carries ``plan_id=<profile_name>`` and the
        aggregated ``reason`` mentions the offending plan id and the
        underlying ``string when`` failure.
        """
        bundle = _write_bundle(tmp_path, "phase_main_outer.yaml", _STRING_PREDICATE_PLAN)
        resolved = _resolved_profile((bundle,))

        with pytest.raises(PlanLiftError) as exc_info:
            validate_profile_plans(resolved)
        err = exc_info.value
        # Top-level error carries profile context.
        assert err.plan_id == "<test>"
        # Aggregated reason names the failing plan and the underlying cause.
        msg = str(err)
        assert "broken.string_predicate" in msg
        assert "string when" in msg

    # ---------------------------------------------------------------------------
    # Port-not-in-source-outputs — typed predicate validation.
    # ---------------------------------------------------------------------------

    def test_unknown_port_in_predicate_raises_at_boot(self, tmp_path: Path) -> None:
        """Typed predicate referencing a non-existent source port fails loud.

        The aggregated ``reason`` includes the inner ``port_name``
        context so debug never relies on log search.
        """
        bundle = _write_bundle(tmp_path, "phase_main_outer.yaml", _UNKNOWN_PORT_PLAN)
        resolved = _resolved_profile((bundle,))

        with pytest.raises(PlanLiftError) as exc_info:
            validate_profile_plans(resolved)
        err = exc_info.value
        assert err.plan_id == "<test>"
        msg = str(err)
        assert "broken.unknown_port" in msg
        assert "nonexistent" in msg

    # ---------------------------------------------------------------------------
    # No termination policy — kernel would run forever.
    # ---------------------------------------------------------------------------

    def test_no_termination_raises_at_boot(self, tmp_path: Path) -> None:
        """A plan without a terminal node / terminal_predicate is rejected."""
        bundle = _write_bundle(tmp_path, "phase_main_outer.yaml", _NO_TERMINATION_PLAN)
        resolved = _resolved_profile((bundle,))

        with pytest.raises(PlanLiftError) as exc_info:
            validate_profile_plans(resolved)
        err = exc_info.value
        assert err.plan_id == "<test>"
        msg = str(err).lower()
        assert "termination" in msg
        assert "broken.no_termination" in msg

    # ---------------------------------------------------------------------------
    # Aggregated errors — user sees all problems at once.
    # ---------------------------------------------------------------------------

    def test_aggregates_errors_across_plans(self, tmp_path: Path) -> None:
        """Multiple bad plans surface all problems in a single failure.

        Outer plan + a ``sub_spec_ref`` it reaches, both malformed.
        The aggregated ``reason`` carries context for both so the
        operator fixes them in one pass instead of N.
        """
        # Inner plan: reached via sub_spec_ref.entry_node, no termination.
        inner = {
            "id": "broken.inner_no_termination",
            "nodes": [
                {
                    "id": "only",
                    "binding": "node_executor",
                    "outputs": ["x"],
                    "entry": True,
                },
            ],
            "edges": [],
        }
        inner_path = _write_bundle(tmp_path, "inner.yaml", inner)
        # Wire the outer to reference the inner via sub_spec_ref.
        outer_mapping = {
            "id": "broken.string_predicate",
            "nodes": [
                {
                    "id": "a",
                    "binding": "node_executor",
                    "outputs": ["decision"],
                    "entry": True,
                    "sub_spec_ref": {
                        "plan_ref": str(Path(inner_path).name),
                        "entry_node": "only",
                    },
                },
                {
                    "id": "b",
                    "binding": "node_executor",
                    "inputs": ["decision"],
                    "terminal": True,
                },
            ],
            "edges": [
                {"from": "a", "to": "b", "when": 'result.payload.x == "y"'},
            ],
        }
        outer_path = _write_bundle(tmp_path, "phase_main_outer.yaml", outer_mapping)
        resolved = _resolved_profile((outer_path,))

        with pytest.raises(PlanLiftError) as exc_info:
            validate_profile_plans(resolved)
        # ``reason`` carries aggregated context for both failing plans.
        msg = str(exc_info.value)
        assert "broken.string_predicate" in msg
        assert "broken.inner_no_termination" in msg
        assert exc_info.value.plan_id == "<test>"

    # ---------------------------------------------------------------------------
    # Empty profile — no plans to validate is a no-op.
    # ---------------------------------------------------------------------------

    def test_empty_profile_passes(self) -> None:
        """A profile with no bundles validates trivially."""
        resolved = _resolved_profile(())
        validate_profile_plans(resolved)  # must not raise
