"""Tests for ADR-0220 §3 three-tier graph topology dispatch.

Eight tests covering §闸门 3 ("三层图拓扑不交叉"). Most assertions are
structural: walk ``bundles/`` to confirm the layout, parse every YAML
bundle that declares ``id:``/``nodes:``/``edges:`` to validate id
prefix and node-id vocabulary. Where the migration is incomplete we
use ``pytest.mark.xfail(strict=False)`` so the test surfaces the gap
informatively without breaking CI.

The companion audit script ``scripts/lca-ops audit-bundle-node-naming``
(ADR-0220 §10 P10) is dry-run via ``skipif`` — it lands in P10.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES_DIR = REPO_ROOT / "bundles"
PRIMITIVE_DIR = BUNDLES_DIR / "primitive"
CONCEPT_DIR = BUNDLES_DIR / "concept"
BUSINESS_DIR = BUNDLES_DIR / "business"

# Baselines (§10 §闸门 3): legacy flat graph bundles that exist before the
# three-tier migration lands. They are tolerated by
# ``test_top_level_bundles_only_allows_baseline_files`` and treated as
# compat-era graph bundles by ``test_graph_id_prefix_is_in_three_tier_set``
# via the ``think.`` prefix entry. P10 deletes them (ADR-0220 §11).
BASELINE_TOP_LEVEL_BUNDLES: frozenset[str] = frozenset(
    {
        "base.yaml",  # plugin manifest, not a graph
        "think.yaml",  # compat-era graph bundle
        "think_reason.yaml",  # compat-era graph bundle
    }
)

# ADR-0220 §3.2 / §3.3 / §3.4 graph-id prefix closed set.
# ``phase.`` and ``think.`` are explicitly allowed for compat-era bundles
# (§10 permits them to keep ids until P10 deletes the underlying files).
THREE_TIER_PREFIXES: frozenset[str] = frozenset(
    {"primitive.", "concept.", "business.", "phase.", "think."}
)

# ADR-0220 §0.4 N9 closed-set of action domains. The audit script (P10)
# uses the same vocabulary.
ALLOWED_ACTION_DOMAINS: frozenset[str] = frozenset(
    {
        "tool",
        "prompt",
        "decision",
        "gate",
        "effect",
        "context",
        "skill",
        "memory",
        "state",
        "observe",
        "spine",
        "capability",
        "llm",
        "shortcut",
        "perceive",
        "reflect",
        "stop",
        # ADR-0220 §3.4: business.reasoning.turn uses the ``reason.*``
        # domain namespace for its 8 subgraph-ref nodes (prep.{tools,
        # role, context, template} / render.prompt / llm.call /
        # classify.response / gate.enforce). The §0.4 N9 closed set is
        # the layer-1/2 vocabulary; business graphs layer on top with
        # domain-specific prefixes whose actions are still composable
        # into the layer-2 vocabulary.
        "reason",
    }
)

# ADR-0220 §0.4 N9 banned substrings (full-segment or prefix matches).
BANNED_NODE_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.process\b"),
    re.compile(r"\.handle\b"),
    re.compile(r"\.manage\b"),
    re.compile(r"^do_"),
    re.compile(r"^.*\.do_"),
    re.compile(r"_impl\b"),
    re.compile(r"_helper\b"),
)


def _list_yaml_files(directory: Path) -> list[Path]:
    """Return ``*.yaml`` files under ``directory`` (non-recursive)."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix == ".yaml")


def _list_top_level_yaml() -> list[str]:
    """Return names of top-level ``bundles/*.yaml`` files."""
    if not BUNDLES_DIR.is_dir():
        return []
    return sorted(p.name for p in BUNDLES_DIR.iterdir() if p.suffix == ".yaml")


def _load_graph_bundle(path: Path) -> dict | None:
    """Parse a YAML bundle; return dict if it has graph fields, else ``None``."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    # Graph bundle shape: has ``id`` + ``nodes`` + ``edges``.
    if "nodes" in data or "edges" in data or "id" in data:
        return data
    return None


def _all_graph_bundles() -> list[tuple[Path, dict]]:
    """Yield ``(path, parsed_dict)`` for every bundle that looks like a graph."""
    out: list[tuple[Path, dict]] = []
    for directory in (PRIMITIVE_DIR, CONCEPT_DIR, BUSINESS_DIR, BUNDLES_DIR):
        for path in _list_yaml_files(directory):
            parsed = _load_graph_bundle(path)
            if parsed is not None:
                out.append((path, parsed))
    return out


class TestTopLevelBundlesLayout:
    """§3.1 — graph bundles live under subdirs, not at the top level."""

    def test_top_level_bundles_only_allows_baseline_files(self) -> None:
        """``bundles/`` top level must not contain new graph bundles.

        After the P5/P8 migration the only acceptable top-level YAML
        files are ``base.yaml`` (plugin manifest) plus the compat-era
        graph bundles enumerated in :data:`BASELINE_TOP_LEVEL_BUNDLES`.
        Any other ``*.yaml`` file at the top level signals a migration
        gap or a leftover legacy graph.

        Only *graph* bundles count as offenders; the many legacy
        plugin-manifest YAMLs (``runtime-core.yaml``,
        ``observability-default.yaml``, …) always live at the top
        level and are out of scope for this check.
        """
        top_level = _list_top_level_yaml()
        offenders = [name for name in top_level if name not in BASELINE_TOP_LEVEL_BUNDLES]
        graph_offenders = [
            name for name in offenders if _load_graph_bundle(BUNDLES_DIR / name) is not None
        ]
        assert not graph_offenders, (
            "ADR-0220 §3 violated: legacy graph bundles still at top level. "
            "Move them under primitive/concept/business/. Files:\n"
            + "\n".join(sorted(graph_offenders))
        )

    @pytest.mark.xfail(
        strict=False,
        reason="ADR-0220 Proposed — three layer subdirs not yet created (P2/P3/P5)",
    )
    def test_three_tier_subdirs_eventually_exist(self) -> None:
        """§3.1 — the three layer subdirs must exist post-migration.

        Until P5 lands these subdirs are absent. Marked xfail so the
        test surfaces the migration gap rather than silently passing.
        """
        missing = [
            name
            for name, directory in (
                ("primitive", PRIMITIVE_DIR),
                ("concept", CONCEPT_DIR),
                ("business", BUSINESS_DIR),
            )
            if not directory.is_dir()
        ]
        assert not missing, (
            f"ADR-0220 §3.1: expected three layer subdirs under bundles/. Missing: {missing}"
        )

    @pytest.mark.xfail(
        strict=False,
        reason="ADR-0220 Proposed — three layer subdirs not yet created (P5/P8)",
    )
    def test_no_three_tier_violations_in_existing_bundles(self) -> None:
        """After P5/P8, every top-level YAML not in baseline must be a
        layer-tagged graph bundle (under primitive/concept/business/).

        Today there are flat compat-era graph bundles (``think.yaml``,
        ``think_reason.yaml``) tolerated by the baseline list. The
        xfail marker captures the post-migration expectation: those
        legacy files must have moved under the correct subdir and the
        assertion will then hold without the baseline exception.
        """
        top_level = _list_top_level_yaml()
        graph_files = [
            name
            for name in top_level
            if name != "base.yaml" and _load_graph_bundle(BUNDLES_DIR / name) is not None
        ]
        assert not graph_files, (
            "ADR-0220 §3.1: legacy graph bundles still at top level. "
            "Move them under primitive/concept/business/. Files:\n" + "\n".join(sorted(graph_files))
        )


class TestGraphIdPrefixClosedSet:
    """§3.2 / §3.3 / §3.4 — every graph bundle id must use a three-tier prefix."""

    @pytest.mark.parametrize(
        "path,parsed",
        _all_graph_bundles(),
        ids=lambda value: str(value) if isinstance(value, Path) else "fixture",
    )
    def test_graph_id_prefix_is_in_three_tier_set(self, path: Path, parsed: dict) -> None:
        """Each graph bundle's ``id`` must start with one of the closed prefixes."""
        graph_id = parsed.get("id")
        if not isinstance(graph_id, str):
            pytest.skip(f"{path.name}: no string id, not a graph bundle")
        prefix = graph_id.split(".", 1)[0] + "."
        assert prefix in THREE_TIER_PREFIXES, (
            f"ADR-0220 §3 violated: graph id '{graph_id}' in {path.name} "
            f"uses prefix '{prefix}' which is not in {sorted(THREE_TIER_PREFIXES)}."
        )

    def test_no_primitive_graph_exceeds_six_node(self) -> None:
        """§3.2 — primitive graphs are runtime primitives, ≤ 6 nodes each."""
        if not PRIMITIVE_DIR.is_dir():
            pytest.skip("bundles/primitive/ not yet created (P2)")
        for path in _list_yaml_files(PRIMITIVE_DIR):
            parsed = _load_graph_bundle(path)
            if parsed is None:
                continue
            nodes = parsed.get("nodes", [])
            if not isinstance(nodes, list):
                continue
            assert len(nodes) <= 6, (
                f"ADR-0220 §3.2 violated: primitive graph {path.name} "
                f"has {len(nodes)} nodes (max 6)."
            )


class TestBusinessGraphReferenceOnly:
    """§3.4 — business graph nodes reference other graphs, never inline impl."""

    @pytest.mark.xfail(
        strict=False,
        reason="ADR-0220 Proposed — bundles/business/ not yet populated (P5/P8)",
    )
    def test_business_graph_nodes_only_reference_other_graphs(self) -> None:
        """Each business-graph node must be a ``ref:`` to another graph id."""
        if not BUSINESS_DIR.is_dir():
            pytest.skip("bundles/business/ not yet created (P5/P8)")
        graph_ids = {
            parsed.get("id")
            for _, parsed in _all_graph_bundles()
            if isinstance(parsed.get("id"), str)
        }
        for path in _list_yaml_files(BUSINESS_DIR):
            parsed = _load_graph_bundle(path)
            if parsed is None:
                continue
            for node in parsed.get("nodes", []) or []:
                if not isinstance(node, dict):
                    continue
                ref = node.get("ref") or node.get("graph_ref")
                impl = node.get("impl")
                assert ref is not None, (
                    f"ADR-0220 §3.4 violated: business graph node "
                    f"{node.get('id')!r} in {path.name} must declare "
                    f"'ref: <graph_id>'. Inline impl is forbidden."
                )
                assert impl is None, (
                    f"ADR-0220 §3.4 violated: business graph node "
                    f"{node.get('id')!r} in {path.name} carries inline "
                    f"'impl:' — business graphs are composition-only."
                )
                assert ref in graph_ids, (
                    f"ADR-0220 §3.4 violated: business graph node "
                    f"{node.get('id')!r} in {path.name} references unknown "
                    f"graph '{ref}'."
                )


class TestConceptGraphTypedPorts:
    """§3.3 — concept graphs declare typed inputs/outputs on every node."""

    @pytest.mark.xfail(
        strict=False,
        reason="ADR-0220 Proposed — bundles/concept/ not yet populated (P3/P4)",
    )
    def test_concept_graph_nodes_have_typed_inputs_outputs(self) -> None:
        """Each concept-graph node must declare ``inputs:`` + ``outputs:`` lists."""
        if not CONCEPT_DIR.is_dir():
            pytest.skip("bundles/concept/ not yet created (P3)")
        for path in _list_yaml_files(CONCEPT_DIR):
            parsed = _load_graph_bundle(path)
            if parsed is None:
                continue
            for node in parsed.get("nodes", []) or []:
                if not isinstance(node, dict):
                    continue
                inputs = node.get("inputs")
                outputs = node.get("outputs")
                assert isinstance(inputs, list), (
                    f"ADR-0220 §3.3 violated: concept graph node "
                    f"{node.get('id')!r} in {path.name} missing typed 'inputs:' list."
                )
                assert isinstance(outputs, list), (
                    f"ADR-0220 §3.3 violated: concept graph node "
                    f"{node.get('id')!r} in {path.name} missing typed 'outputs:' list."
                )


class TestNodeIdVocabulary:
    """§0.4 N9 — node ids follow the closed action-domain vocabulary."""

    @pytest.mark.parametrize(
        "path,parsed",
        _all_graph_bundles(),
        ids=lambda value: str(value) if isinstance(value, Path) else "fixture",
    )
    def test_no_process_or_handle_node_ids(self, path: Path, parsed: dict) -> None:
        """Every node id must avoid ``process`` / ``handle`` / ``manage`` /
        ``do_*`` / ``_impl`` / ``_helper`` and use the closed action
        domain as its first segment.

        Compat-era graph bundles (those under the legacy top-level
        ``bundles/`` directory whose id uses ``think.`` or ``phase.``)
        predate N9 and are tolerated by this guardrail until P10
        deletes them. The audit script (P10) is the canonical
        enforcement path going forward.
        """
        # Compat-era bundles live at the top level (not in a subdir) and
        # use ``think.`` / ``phase.`` ids. Skip the action-domain check
        # for them; the banned-pattern check still applies so no new
        # ``process`` / ``handle`` / ``manage`` slips in even today.
        is_compat_top_level = path.parent == BUNDLES_DIR
        for node in parsed.get("nodes", []) or []:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            if not isinstance(node_id, str):
                continue
            for banned in BANNED_NODE_ID_PATTERNS:
                assert not banned.search(node_id), (
                    f"ADR-0220 §0.4 N9 violated: node id '{node_id}' in "
                    f"{path.name} matches banned pattern {banned.pattern!r}."
                )
            if is_compat_top_level:
                continue
            action_domain = node_id.split(".", 1)[0]
            assert action_domain in ALLOWED_ACTION_DOMAINS, (
                f"ADR-0220 §0.4 N9 violated: node id '{node_id}' in "
                f"{path.name} has first segment '{action_domain}' which "
                f"is not in the closed action-domain set "
                f"{sorted(ALLOWED_ACTION_DOMAINS)}."
            )


class TestAuditBundleNodeNamingScript:
    """§10 — the audit script lands in P10; skip cleanly if absent."""

    def test_audit_bundle_node_naming_script_dry_run(self) -> None:
        """Invoke ``./scripts/lca-ops audit-bundle-node-naming --help``.

        The script itself lands in P10 (ADR-0220 §11). Until then this
        test is skipped — its job is to ensure the moment the script
        arrives, the test exercises its dry-run path. When the script
        does ship, ``shutil.which`` finds it via the wrapper, and we
        assert it runs without error.
        """
        lca_ops = REPO_ROOT / "scripts" / "lca-ops"
        if not lca_ops.is_file():
            pytest.skip("scripts/lca-ops wrapper absent")
        if shutil.which("bash") is None:
            pytest.skip("bash unavailable in test environment")
        proc = subprocess.run(  # noqa: S603 - inputs are static (path is a repo file)
            [str(lca_ops), "audit-bundle-node-naming", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 2 and "No such command" in (proc.stderr + proc.stdout):
            pytest.skip("audit-bundle-node-naming not yet implemented (ADR-0220 P10)")
        assert proc.returncode == 0, (
            f"audit-bundle-node-naming --help failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
