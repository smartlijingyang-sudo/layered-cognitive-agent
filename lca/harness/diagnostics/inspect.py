"""Inspect a resolved plugin tree (``lca-ops inspect-tree``)."""

from __future__ import annotations

from pathlib import Path


async def inspect_profile_tree(profile_path: Path | str):
    """Boot a profile and return the resolved cordis.Context."""

    from lca.harness.profile.boot import boot_profile

    return await boot_profile(profile_path)


def format_plugin_tree(ctx: Context, *, profile: str) -> str:
    """Render a human-readable plugin tree dump from a cordis Context.

    Inspects the Context's fiber for entries and dumps them as a
    human-readable listing. The full implementation is deferred to Chunk 6
    (lca-ops debug tree); this stub returns a minimal summary.
    """
    lines = [
        f"Profile: {profile}",
        f"Plugin count: {sum(1 for k in dir(ctx) if not k.startswith('_'))}",
        "",
    ]
    lines.append("(Detailed plugin tree dump: see Chunk 6 lca-ops debug tree)")
    lines.append("")
    return "\n".join(lines)
