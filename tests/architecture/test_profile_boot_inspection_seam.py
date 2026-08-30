"""Architecture guard: inspection reads Profile boot products, not Context.entries."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from gateway.runs.session.setup import plugin_inventory_from_boot_products
from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.harness.diagnostics.inspect import format_capability_graph, format_plugin_tree
from lca.harness.profile.boot import boot_entries, boot_profile, load_profile_entries
from lca.harness.profile.boot_products import (
    compiled_plan_from_scope,
    profile_boot_products_from_scope,
    resolved_profile_from_scope,
)

REPO = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (REPO / "lca", REPO / "gateway")
FORBIDDEN_SNIPPETS = (
    '__dict__["entries"]',
    "__dict__['entries']",
    '__dict__.get("entries")',
    "__dict__.get('entries')",
    'getattr(ctx, "entries"',
    "getattr(ctx, 'entries'",
    'getattr(self._ctx, "entries"',
    "getattr(self._ctx, 'entries'",
)
FIXTURE_PROFILE = "profiles/test-minimal.yaml"


def _production_entries_guesses() -> list[str]:
    """Locate production reads/writes of the retired Context.entries attribute."""

    violations: list[str] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            text = path.read_text(encoding="utf-8")
            for snippet in FORBIDDEN_SNIPPETS:
                if snippet in text:
                    violations.append(f"{rel}: {snippet}")
    return violations


def test_production_code_does_not_guess_context_entries() -> None:
    """Diagnostics and lifecycle must read the boot-products seam only."""

    assert not _production_entries_guesses(), (
        "Production code must not write or guess Context.entries; "
        "inspection views are derived from resolved_profile on the boot-products seam.\n"
        + "\n".join(_production_entries_guesses())
    )


def test_programmatic_boot_attaches_resolved_profile_without_context_entries() -> None:
    """The compatibility entrance shares the inspection seam, not a compiled plan."""

    ctx = asyncio.run(boot_entries(load_profile_entries(FIXTURE_PROFILE)))

    assert "entries" not in ctx.__dict__
    products = profile_boot_products_from_scope(ctx)
    assert products is not None
    assert products.resolved_profile is resolved_profile_from_scope(ctx)
    assert products.resolved_profile is not None
    assert products.compiled_run_plan is None
    tree = format_plugin_tree(ctx, profile="programmatic")
    assert "manifest_hash:" in tree
    assert products.resolved_profile.manifest_hash in tree
    graph = format_capability_graph(ctx, profile="programmatic")
    assert graph["manifest_hash"] == products.resolved_profile.manifest_hash
    assert graph["nodes"]
    with pytest.raises(MissingCapabilityError, match="compiled_run_plan"):
        compiled_plan_from_scope(ctx)


def test_run_plugin_inventory_reads_boot_products_not_context_entries() -> None:
    """Run diagnostics must ignore a stale dynamic entries attribute."""

    ctx = asyncio.run(boot_profile(FIXTURE_PROFILE))
    resolved = resolved_profile_from_scope(ctx)
    assert resolved is not None
    ctx.__dict__["entries"] = (
        SimpleNamespace(id="stale.plugin", inject=("wrong",), provides=("wrong",)),
    )

    assert plugin_inventory_from_boot_products(ctx) == [
        "|".join(
            (
                entry.id,
                f"requires={','.join(entry.definition.required_capability_keys)}",
                f"provides={','.join(entry.definition.provided_capability_keys)}",
            )
        )
        for entry in resolved.plugins
        if not entry.disabled
    ]


def test_production_boot_inspection_reads_the_attached_resolved_profile() -> None:
    """A file Profile boot must expose inspection through the same fact pair."""

    ctx = asyncio.run(boot_profile(FIXTURE_PROFILE))

    assert "entries" not in ctx.__dict__
    resolved = resolved_profile_from_scope(ctx)
    assert resolved is not None
    tree = format_plugin_tree(ctx, profile="test-minimal")
    assert resolved.manifest_hash in tree
    graph = format_capability_graph(ctx, profile="test-minimal")
    assert graph["manifest_hash"] == resolved.manifest_hash
