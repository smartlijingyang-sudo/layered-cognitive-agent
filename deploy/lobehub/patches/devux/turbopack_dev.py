"""Patch: turbopack_dev — Enable Turbopack for faster dev compilation."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="turbopack_dev",
    description="Enable Turbopack for faster dev compilation",
    files=("scripts/devStartupSequence.mts",),
    risk="low",
    category="devux",
    depends_on=(),
    why="Turbopack significantly speeds up Next.js dev builds",
    technical_detail="Add '--turbo' flag to the next dev command in devStartupSequence.",
    verify_file="scripts/devStartupSequence.mts",
    verify_marker="'--turbo'",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "scripts/devStartupSequence.mts"
    if ctx.has_marker(rel, "'--turbo'"):
        return False
    old = "spawn('bunx', ['next', 'dev', '-p', String(nextPort)]"
    new = "spawn('bunx', ['next', 'dev', '--turbo', '-p', String(nextPort)]"
    text = ctx.replace_once(rel, old, new, label="turbopack_dev")
    ctx.write(rel, text)
    return True
