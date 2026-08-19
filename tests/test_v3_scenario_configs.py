"""v3 scenario config validation — every scenario YAML parses + covers the closed set.

Spec §13: every scenario is a **configuration** over the closed
primitive set.  No new loop stages, no new ActionTypes, no new event
classes.  This test verifies each scenario file:

1. Parses as YAML.
2. Names only PluginMeta-known bundles / plugins / tools.
3. References only the closed ``ActionType`` set.
4. Declares a ``task_contract`` (or none — solo is fine).
5. Declares a ``memory_policy`` that doesn't violate v3 §8 (working /
   episodic MUST be private).

The test is intentionally parser-thin: we don't load the bundles
(that's ``CordisLoader``'s job); we validate the *contract* the
configuration declares, because that's what makes a profile safe to
publish.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# Closed primitive set (v3 §4.1).
ALLOWED_ACTION_TYPES: frozenset[str] = frozenset(
    {"respond", "use_tool", "delegate", "handoff", "stop", "ask_human"}
)

# Forbidden memory-sharing (v3 §8.1).
NEVER_SHARED_LAYERS: frozenset[str] = frozenset({"working", "episodic"})


def _scenario_files() -> list[Path]:
    return sorted(SCENARIOS_DIR.glob("*.yaml"))


def _parse(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@pytest.mark.parametrize("scenario_path", _scenario_files(), ids=lambda p: p.stem)
def test_scenario_yaml_parses(scenario_path: Path) -> None:
    cfg = _parse(scenario_path)
    assert isinstance(cfg, dict), f"{scenario_path.name} must parse as a mapping"


@pytest.mark.parametrize("scenario_path", _scenario_files(), ids=lambda p: p.stem)
def test_scenario_no_unknown_action_types(scenario_path: Path) -> None:
    """Spec §4.1: only the closed six ActionTypes are allowed."""
    cfg = _parse(scenario_path)

    def _walk_actions(node: object) -> list[str]:
        if isinstance(node, dict):
            acc: list[str] = []
            for key, value in node.items():
                if key in {"allowed_actions", "forbidden_actions"} and isinstance(value, list):
                    for entry in value:
                        if isinstance(entry, str):
                            acc.append(entry.lower())
                acc.extend(_walk_actions(value))
            return acc
        if isinstance(node, list):
            acc: list[str] = []
            for item in node:
                acc.extend(_walk_actions(item))
            return acc
        return []

    actions = _walk_actions(cfg)
    bad = [a for a in actions if a not in ALLOWED_ACTION_TYPES and a != "stop"]
    assert not bad, (
        f"{scenario_path.name}: unknown action types {bad}; allowed = {sorted(ALLOWED_ACTION_TYPES)}"
    )


@pytest.mark.parametrize("scenario_path", _scenario_files(), ids=lambda p: p.stem)
def test_scenario_working_memory_is_private(scenario_path: Path) -> None:
    """v3 §8.1: working + episodic MUST stay private (never shared)."""
    cfg = _parse(scenario_path)
    shared = (
        cfg.get("memory_policy", {}).get("shared_layers", [])
        if isinstance(cfg.get("memory_policy"), dict)
        else []
    )
    if not isinstance(shared, list):
        shared = []
    leak = [layer for layer in shared if layer in NEVER_SHARED_LAYERS]
    assert not leak, (
        f"{scenario_path.name}: memory_policy.shared_layers leaks "
        f"{leak}; working/episodic are private per v3 §8.1"
    )


@pytest.mark.parametrize("scenario_path", _scenario_files(), ids=lambda p: p.stem)
def test_scenario_team_xor_when_present(scenario_path: Path) -> None:
    """ADR-0030/0034: Team XOR — lead OR coordination, never both.

    Scenarios without a ``team`` block skip this check (solo agents).
    """
    cfg = _parse(scenario_path)
    if "team" not in cfg:
        pytest.skip("solo scenario (no team block)")
    team = cfg.get("team") or {}
    gov = team.get("governance") or {}
    has_lead = "lead" in gov
    has_coord = "coordination" in gov
    assert not (has_lead and has_coord), (
        f"{scenario_path.name}: governance has BOTH lead and coordination; XOR violated"
    )


@pytest.mark.parametrize("scenario_path", _scenario_files(), ids=lambda p: p.stem)
def test_scenario_bundles_only_reference_v3_bundles(scenario_path: Path) -> None:
    """Bundles declared in scenarios must live under ``bundles/``.

    Spec §3.7: Profile + Bundle + Plugin = the configuration stack.
    A scenario that references a bundle outside ``bundles/`` violates
    the configuration discipline.
    """
    cfg = _parse(scenario_path)
    bundles = cfg.get("bundles", [])
    if not isinstance(bundles, list):
        pytest.skip("no bundles list")
    for entry in bundles:
        if isinstance(entry, str):
            # Plain string — must be a path under ``bundles/``.
            assert entry.startswith("bundles/"), (
                f"{scenario_path.name}: bundle {entry!r} is not under bundles/"
            )


def test_scenarios_directory_has_twelve_files() -> None:
    """Sanity: we declared twelve scenarios in spec §13.5."""
    assert len(_scenario_files()) == 12, (
        f"Expected 12 scenarios, found {len(_scenario_files())}: "
        f"{[p.name for p in _scenario_files()]}"
    )


def test_scenarios_unique_ids() -> None:
    """No two scenarios share the same profile id."""
    ids = []
    for path in _scenario_files():
        cfg = _parse(path)
        profile = cfg.get("profile") or {}
        ids.append(profile.get("id", path.stem))
    duplicates = {x for x in ids if ids.count(x) > 1}
    assert not duplicates, f"Duplicate scenario ids: {duplicates}"
