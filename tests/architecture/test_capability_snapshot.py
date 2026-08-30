"""Capability snapshot and fallback allowlist tests — ADR-0076 / W0 baseline.

These tests enforce:
1. Plan ref stability: the same profile produces the same plan_ref hash
2. Fallback allowlist does not grow without justification
3. Capability owners are unique (no duplicate provides)
4. No reverse layer dependencies
5. Plugin classification into six planes is deterministic

W0 baseline acceptance criteria:
- Same profile generates stable plan_ref locally and in CI
- New plugin not in bundle is not misjudged as running capability
- Undeclared capability, duplicate owner, reverse layer dependency fail at static gate
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import scripts.snapshot_capability_tree as snapshot
from scripts.snapshot_capability_tree import (
    _build_capability_tree,
    _load_fallback_allowlist,
    _scan_plugins,
)

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROFILE = "profiles/web-standard.yaml"

# ── W0 §任务: Fallback allowlist ──────────────────────────────────────

# Maximum allowed fallback entries. This number should NOT grow without
# explicit justification in the allowlist entry itself.
MAX_FALLBACK_COUNT = 10


def test_fallback_allowlist_size() -> None:
    """Fallback allowlist must not exceed MAX_FALLBACK_COUNT.

    Each entry must have: location, kind, reason, scope, removal_target.
    The allowlist is tracked in ``_load_fallback_allowlist()``.
    """
    allowlist = _load_fallback_allowlist()
    assert len(allowlist) <= MAX_FALLBACK_COUNT, (
        f"Fallback allowlist exceeds {MAX_FALLBACK_COUNT} entries. "
        f"Found {len(allowlist)}. Each entry must have removal_target. "
        "See W0 §任务 for allowlist schema."
    )
    for entry in allowlist:
        assert "location" in entry, f"Entry missing 'location': {entry}"
        assert "kind" in entry, f"Entry missing 'kind': {entry}"
        assert "reason" in entry, f"Entry missing 'reason': {entry}"
        assert "scope" in entry, f"Entry missing 'scope': {entry}"
        assert "removal_target" in entry, f"Entry missing 'removal_target': {entry}"
        assert entry["scope"] in {"test", "production", "both"}, (
            f"Invalid scope {entry['scope']!r}; must be test/production/both"
        )


def test_fallback_allowlist_has_no_retired_runtime_factory_entry() -> None:
    """生产 capability 图不得重新报告已退出的 fixture-only 默认装配。"""
    assert _load_fallback_allowlist() == []


# ── Plan ref stability ────────────────────────────────────────────────


def test_plan_ref_stability() -> None:
    """Same profile must produce the same plan_ref hash.

    The plan_ref is a deterministic SHA-256 hash of:
    - Profile path
    - Bundle list (sorted)
    - Plugin list (sorted by id): id, module, layer, kind, provides, requires

    This test asserts that the plan_ref for the default profile is stable.
    If this test fails, it means the snapshot logic changed or the profile
    structure changed. Update the expected hash below.
    """
    tree = _build_capability_tree(DEFAULT_PROFILE)
    # The plan_ref should be stable across runs
    # If this fails, the snapshot logic or profile structure changed
    assert len(tree.plan_ref) == 16, f"plan_ref should be 16 chars, got {len(tree.plan_ref)}"
    assert tree.plan_ref.isalnum(), f"plan_ref should be alphanumeric, got {tree.plan_ref}"
    # Re-build and assert same hash
    tree2 = _build_capability_tree(DEFAULT_PROFILE)
    assert tree.plan_ref == tree2.plan_ref, (
        f"plan_ref not stable: {tree.plan_ref} != {tree2.plan_ref}"
    )


def test_plan_ref_is_independent_of_checkout_path() -> None:
    """Equivalent relative and absolute Profile inputs share one plan identity."""
    from lca.harness.plan import compiled_run_plan_ref
    from lca.harness.profile.plan_compiler import compile_plan
    from lca.harness.profile.resolve import resolve_profile

    relative_plan = compile_plan(resolve_profile(DEFAULT_PROFILE))
    absolute_plan = compile_plan(resolve_profile(REPO / DEFAULT_PROFILE))

    assert relative_plan.profile_path == absolute_plan.profile_path == DEFAULT_PROFILE
    assert compiled_run_plan_ref(relative_plan) == compiled_run_plan_ref(absolute_plan)


# ── Capability ownership is production-resolved ───────────────────────


def test_capability_owners_match_production_profile_resolution() -> None:
    """The snapshot must expose the same unique ownership facts as production.

    ``resolve_profile`` rejects duplicate ``provides`` entries before boot. The
    diagnostic tree must consume that same seam, rather than silently choosing
    a first owner and reinterpreting later providers as contributors.
    """
    from lca.harness.profile.resolve import resolve_profile

    tree = _build_capability_tree(DEFAULT_PROFILE)
    resolved = resolve_profile(REPO / DEFAULT_PROFILE)
    expected = {
        capability: plugin.id
        for plugin in sorted(resolved.plugins, key=lambda item: item.id)
        if not plugin.disabled
        for capability in plugin.definition.provided_capability_keys
    }

    assert tree.capability_owners == expected


# ── No reverse layer dependencies ─────────────────────────────────────


def test_no_reverse_layer_dependencies() -> None:
    """Plugins must not have reverse layer dependencies.

    Layer order: L0 < L1 < L2 < L3 < L4
    A plugin at layer L_n must not require a capability provided by L_m where m > n.
    """
    tree = _build_capability_tree(DEFAULT_PROFILE)
    layer_order = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}

    # Build capability → layer map
    cap_layer: dict[str, int] = {}
    for plugin in tree.plugins:
        layer_num = layer_order.get(plugin.layer, 0)
        for cap in plugin.provides:
            if cap not in cap_layer:
                cap_layer[cap] = layer_num

    # Check each plugin's requires
    violations: list[str] = []
    for plugin in tree.plugins:
        plugin_layer = layer_order.get(plugin.layer, 0)
        for req in plugin.requires:
            if req in cap_layer:
                req_layer = cap_layer[req]
                if req_layer > plugin_layer:
                    violations.append(
                        f"{plugin.id} (L{plugin_layer}) requires {req} from L{req_layer}"
                    )

    assert not violations, f"Found {len(violations)} reverse layer dependencies:\n" + "\n".join(
        f"  - {v}" for v in violations
    )


# ── Plugin classification is deterministic ────────────────────────────


def test_plugin_classification_deterministic() -> None:
    """Plugin plane classification must be deterministic.

    Re-scanning the same plugins must produce the same plane assignments.
    """
    plugins1 = _scan_plugins()
    plugins2 = _scan_plugins()

    assert len(plugins1) == len(plugins2), "Plugin scan count mismatch"

    # Sort by id for comparison
    by_id1 = {p.id: p for p in plugins1}
    by_id2 = {p.id: p for p in plugins2}

    assert set(by_id1.keys()) == set(by_id2.keys()), "Plugin id sets differ"

    for pid, p1 in by_id1.items():
        p2 = by_id2[pid]
        assert p1.plane == p2.plane, (
            f"Plugin {pid} plane not deterministic: {p1.plane} != {p2.plane}"
        )


# ── Golden fixture: plan_ref snapshot ─────────────────────────────────


def test_unbundled_plugin_does_not_change_plan_ref(monkeypatch) -> None:
    """A plugin outside the selected profile must not alter its plan identity."""
    baseline = snapshot._build_capability_tree(DEFAULT_PROFILE)
    original_scan = snapshot._scan_plugins
    template = baseline.plugins[0]
    unrelated = replace(
        template,
        id="synthetic-unbundled-plugin",
        module="lca.plugins.synthetic.unbundled",
    )
    monkeypatch.setattr(snapshot, "_scan_plugins", lambda: [*original_scan(), unrelated])

    changed = snapshot._build_capability_tree(DEFAULT_PROFILE)

    assert changed.plan_ref == baseline.plan_ref
    assert all(plugin.id != unrelated.id for plugin in changed.plugins)


def test_golden_plan_ref_snapshot() -> None:
    """Golden fixture: save the plan_ref to a file for CI comparison.

    This test saves the current plan_ref to tests/fixtures/plan_ref_golden.txt.
    CI can compare this file against the current plan_ref to detect changes.
    """
    tree = _build_capability_tree(DEFAULT_PROFILE)
    golden_path = REPO / "tests" / "fixtures" / "plan_ref_golden.txt"
    golden_path.parent.mkdir(parents=True, exist_ok=True)

    if golden_path.exists():
        saved_ref = golden_path.read_text(encoding="utf-8").strip()
        # If the saved ref differs, it means the profile structure changed
        # This is expected during development; update the golden file
        if saved_ref != tree.plan_ref:
            # For now, just assert they match or the golden file is empty
            # In CI, this would fail if the plan_ref changed without updating the golden file
            assert saved_ref == tree.plan_ref, (
                f"plan_ref changed: golden={saved_ref}, current={tree.plan_ref}. "
                f"If this is expected, update {golden_path}"
            )
    else:
        # First run: save the current plan_ref
        golden_path.write_text(tree.plan_ref + "\n", encoding="utf-8")


# ── JSON output is valid ─────────────────────────────────────────────


def test_json_output_valid() -> None:
    """JSON output must be valid and contain expected fields."""
    import shutil
    import subprocess

    uv = shutil.which("uv")
    assert uv is not None, "project test environment must provide uv"
    result = subprocess.run(  # noqa: S603 - executable and arguments are fixed repository test inputs
        [uv, "run", "python", "scripts/snapshot_capability_tree.py", "--json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert "plan_ref" in data
    assert "profile" in data
    assert "bundles" in data
    assert "plugins" in data
    assert "capability_owners" in data
    assert "plane_summary" in data
    assert "fallback_allowlist" in data
    assert isinstance(data["plugins"], list)
    assert len(data["plugins"]) > 0
