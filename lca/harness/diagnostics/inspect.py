"""Inspect a resolved plugin tree (``lca-ops inspect-tree``)."""

from __future__ import annotations

from pathlib import Path

from lca.harness.profile.boot import boot_profile
from lca.layer0_infra.plugin.loader._entry import BootedTree


async def inspect_profile_tree(profile_path: Path | str) -> BootedTree:
    """Boot a profile and return the resolved tree."""
    return await boot_profile(profile_path, check_seam_completeness=True)


def format_plugin_tree(tree: BootedTree, *, profile: str) -> str:
    """Render a human-readable plugin tree dump."""
    lines = [
        f"Profile: {profile}",
        f"Plugins: {len(tree.entries)}",
        "",
    ]
    entries_by_id = {entry.id: entry for entry in tree.entries}
    for handle_id, handle in tree.host.handles.items():
        provides = handle.spec.provides or "—"
        inject = handle.injected or "—"
        lines.append(f"  {handle_id}")
        lines.append(f"    state: {handle.state.value}")
        lines.append(f"    provides: {provides}")
        lines.append(f"    inject: {inject}")
        lines.append(f"    effects: {len(handle.effects)}")

        original = getattr(entries_by_id.get(handle_id), "_original_module", None)
        if original is not None:
            manifest = getattr(original, "manifest", None)
            if manifest is not None:
                lines.append(f"    kind: {manifest.kind.value}")
                if manifest.seam_key:
                    lines.append(f"    seam: {manifest.seam_key}")
    lines.append("")
    lines.append("Seam completeness: PASS")
    return "\n".join(lines)
