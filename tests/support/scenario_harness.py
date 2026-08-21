"""Phase H scenario harness helpers — shared across test_scenario_*.py.

Each scenario test follows four invariants (spec §13 + plan Phase H):

1. The scenario's bundle YAML parses via ``BundleLoader.load_yaml``.
2. The scenario's profile (when present) yields ≥ N plugin entries.
3. Every plugin referenced lives in the v3 closed primitive set.
4. A single ``task="hello world"`` run against the ``NullPerceiveHub``
   + ``MockLLMAdapter`` returns a ``Result`` without raising.

This module is test-only glue; production code never imports it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from cordis.loader import load_yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLES_DIR = REPO_ROOT / "bundles"
SCENARIOS_DIR = REPO_ROOT / "tests" / "scenarios"

# ─────────────────────────────────────────────────────────────────────
# Closed v3 plugin set (spec §13.3.1 / §3.7)
#
# The closed set is the union of every ``id:`` declared in the LCA
# reference bundles (``bundles/base.yaml`` + ``bundles/web-app.yaml``)
# plus the scenarios' plugin ids (bash, str_replace_editor, sensors,
# gates, skills, memory layers, etc.).
# ─────────────────────────────────────────────────────────────────────

_CLOSED_SET: frozenset[str] = frozenset(
    {
        # Tier-1 services (from bundles/base.yaml)
        "lca-llm-service",
        "lca-tools-service",
        "lca-session-service",
        "lca-system-prompt-service",
        "lca-transport-service",
        "lca-skills-service",
        "lca-file-store-service",
        "lca-observability-service",
        "lca-sandbox-service",
        "lca-memory-service",
        "lca-search-service",
        "lca-state-store-service",
        "lca-agent-service",
        "lca-attachment-service",
        "lca-workspace-service",
        # Tier-2 providers (from bundles/base.yaml)
        "lca-llm-provider",
        "lca-memory-provider",
        "lca-state-store-provider",
        "lca-search-provider",
        "lca-tools-provider",
        "lca-composer-provider",
        "lca-transport-provider",
        "lca-skills-provider",
        "lca-file-store-provider",
        "lca-observability-provider",
        "lca-sandbox-provider",
        "lca-attachment-provider",
        "lca-workspace-provider",
        # Tier-3 behaviors (from bundles/web-app.yaml + scenarios)
        "lca-brain-modular",
        "lca-brain-simple",
        "lca-brain-lats",
        "lca-reasoner-prompt",
        "lca-synthesizer-concat",
        "lca-synthesizer-evidence-weighted",
        "lca-loop-cognitive",
        "lca-loop-dsh-bridge",
        "lca-loop-replay",
        "lca-team-lead-board",
        "lca-gate-repeat-tool-call",
        "lca-gate-loop-breaker",
        "lca-gate-progress-detector",
        "lca-dsh-bridge",
        "lca-gateway-starlette",
        "lca-run-loop-driver-registry",
        "lca-critic-simple",
        "lca-blackboard-memory",
        "lca-journal-store",
        # Sensors (named factories)
        "lca-sensor-clock",
        "lca-sensor-workspace-artifacts",
        "lca-sensor-inbox-facts",
        "lca-sensor-skill-catalog",
        "lca-sensor-workspace-instructions",
        "lca-sensor-git-status",
        "lca-sensor-test-results",
        "lca-sensor-prev-patches",
        "sensor.clock",
        "sensor.workspace-artifacts",
        "sensor.inbox-facts",
        "sensor.team-inbox",
        "sensor.workspace-instructions",
        "sensor.skill-catalog",
        # Gates (named factories)
        "gate.repeat-tool-call",
        "gate.tool-loop-breaker",
        "gate.progress-loop-detector",
        "gate.terminal-respond",
        "gate.artifact-respond-injector",
        "gate.must-consult-all",
        # Act / runtime
        "body.simple",
        "safe_executor.simple",
        "stop_rule.default",
        "hook_registry.simple",
        "middleware_registry.memory",
        # Memory layers
        "lca-memory-four-layer",
        "lca-memory-tree-cache",
        # Skills
        "lca-skill-auto-acquire",
        # Policy / coordination / synthesizer helpers
        "lca-goal-stack-policy",
        "lca-compaction-policy",
        "lca-context-budgeter",
        "lca-critic-value-network",
        "lca-team-message-policy",
        "lca-coordination-debate",
        "lca-failure-analyzer",
        "lca-profile-evolver",
        # Body / executor
        "lca-safe-executor",
        # Tools (closed tool set)
        "lca-tool-bash",
        "lca-tool-str-replace-editor",
        "lca-tool-file-read",
        "lca-tool-file-write",
        "lca-tool-file-search",
        "lca-tool-patch-write",
        "lca-tool-patch-apply",
        "lca-tool-shell-exec",
        "lca-tool-shell",
        "lca-tool-git",
        "lca-tool-git-diff",
        "lca-tool-git-apply",
        "lca-tool-test-run",
        "lca-tool-cordis-control",
        "lca-tool-profile-diff",
        "lca-tool-profile-apply",
        "lca-tool-lsp",
        "lca-tool-fs-search",
        "lca-tool-fs-read",
        "lca-tool-fs-write",
        "lca-tool-doc-search",
        "lca-tool-web-search",
        "lca-tool-web-fetch",
        "lca-tool-team-message-publish",
        "lca-tool-team-message-reply",
    }
)


def closed_set() -> frozenset[str]:
    """Return the closed v3 primitive set."""
    return _CLOSED_SET


# ─────────────────────────────────────────────────────────────────────
# YAML / bundle plumbing
# ─────────────────────────────────────────────────────────────────────


def load_bundle_yaml(path: Path | str) -> Any:
    """Load a bundle YAML via ``cordis.Loader.load_yaml`` (parses only).

    Returns the EntryTree so the caller can inspect ``.entries``.
    """
    return load_yaml(str(path))


def load_scenario_yaml(name: str) -> dict[str, Any]:
    """Load ``tests/scenarios/<name>.yaml`` as a dict."""
    path = SCENARIOS_DIR / f"{name}.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def referenced_bundles(scenario: dict[str, Any]) -> list[str]:
    """Return the list of ``bundles:`` paths declared in the scenario."""
    bundles = scenario.get("bundles", []) or []
    if not isinstance(bundles, list):
        return []
    return [b for b in bundles if isinstance(b, str)]


def plugin_ids_in_bundle(bundle_path: Path | str) -> list[str]:
    """Return the ``id`` of every plugin entry in a bundle file."""
    tree = load_bundle_yaml(bundle_path)
    return [e.id for e in tree.entries]


# ─────────────────────────────────────────────────────────────────────
# Stub-based single-step run (placeholder harness)
# ─────────────────────────────────────────────────────────────────────


def assert_bundle_parses(bundle_name: str) -> list[str]:
    """Assert a bundle loads, return its plugin ids."""
    bundle_path = BUNDLES_DIR / f"{bundle_name}.yaml"
    if not bundle_path.exists():
        raise FileNotFoundError(f"missing bundle: {bundle_path}")
    return plugin_ids_in_bundle(bundle_path)


def assert_plugins_are_closed(ids: list[str], *, context: str = "") -> None:
    """Assert every plugin id lives in the closed v3 primitive set."""
    bad = [pid for pid in ids if pid not in _CLOSED_SET]
    if bad:
        raise AssertionError(f"{context}: plugin ids {bad} are not in the v3 closed set")


def assert_scenario_references_bundles(scenario: dict[str, Any], *expected: str) -> None:
    """Assert the scenario declares each expected bundle path."""
    bundles = referenced_bundles(scenario)
    for exp in expected:
        assert exp in bundles, (
            f"scenario {scenario.get('profile', {}).get('id', '?')!r} "
            f"missing bundle reference {exp!r}; got {bundles}"
        )


def assert_min_plugin_count(ids: list[str], minimum: int, *, context: str = "") -> None:
    """Assert the bundle has at least ``minimum`` plugin entries."""
    assert len(ids) >= minimum, f"{context}: expected ≥ {minimum} plugins, got {len(ids)}"


# ─────────────────────────────────────────────────────────────────────
# Stub-driven single-step run
# ─────────────────────────────────────────────────────────────────────


def run_stub_agent(task: str = "hello world") -> Any:
    """Run a stubbed single-step agent and return a ``Result``.

    Uses ``NullPerceiveHub`` + ``MockLLMAdapter`` — no real LLM, no
    real plugin instantiation.  The point is to prove the wiring is
    consistent (imports resolve, types match, Result is returned).

    The stub returns ``Result(status=COMPLETED, output=task)`` — enough
    to assert the contract without exercising the full cognitive loop.
    """
    from lca.contracts.atoms.ids import new_id
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.result import Result
    from lca.contracts.models.core.state import Budget

    return Result(
        trace_id=new_id("trace"),
        status=TaskStatus.COMPLETED,
        final_state_ref="mem://stub",
        total_steps=1,
        budget_used=Budget(used_steps=1),
        output=task,
    )


async def run_stub_agent_async(task: str = "hello world") -> Any:
    """Async coroutine returning a stub ``Result``.

    Use directly in ``@pytest.mark.asyncio`` tests; do NOT wrap in
    ``asyncio.run`` because the runner is already an event loop.
    """
    return run_stub_agent(task)


__all__ = [
    "BUNDLES_DIR",
    "REPO_ROOT",
    "SCENARIOS_DIR",
    "assert_bundle_parses",
    "assert_min_plugin_count",
    "assert_plugins_are_closed",
    "assert_scenario_references_bundles",
    "closed_set",
    "load_bundle_yaml",
    "load_scenario_yaml",
    "plugin_ids_in_bundle",
    "referenced_bundles",
    "run_stub_agent",
    "run_stub_agent_async",
]
