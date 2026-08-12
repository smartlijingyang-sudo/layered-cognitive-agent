"""Patch: default_model — Set default model/provider to solo/openai."""

from __future__ import annotations

import re

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="default_model",
    description="Set default model/provider to solo/openai",
    files=(
        "packages/business/const/src/llm.ts",
        "apps/desktop/stubs/business-const/src/index.ts",
    ),
    risk="low",
    category="provider",
    depends_on=(),
    why="LCA's virtual model 'solo' must be the default for new conversations",
    technical_detail=(
        "Replace DEFAULT_MODEL, DEFAULT_PROVIDER, DEFAULT_MINI_MODEL, DEFAULT_MINI_PROVIDER "
        "in both web and desktop const stubs with LCA defaults (solo/openai)."
    ),
    verify_file="packages/business/const/src/llm.ts",
    verify_marker="DEFAULT_MODEL = 'solo'",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    model = "solo"
    provider = "openai"
    changed = False
    for rel in (
        "packages/business/const/src/llm.ts",
        "apps/desktop/stubs/business-const/src/index.ts",
    ):
        if not ctx.path(rel).is_file():
            continue
        text = ctx.read(rel)
        pairs = [
            (r"export const DEFAULT_MODEL = '[^']*';", f"export const DEFAULT_MODEL = '{model}';"),
            (
                r"export const DEFAULT_PROVIDER = '[^']*';",
                f"export const DEFAULT_PROVIDER = '{provider}';",
            ),
            (
                r"export const DEFAULT_MINI_MODEL = '[^']*';",
                f"export const DEFAULT_MINI_MODEL = '{model}';",
            ),
            (
                r"export const DEFAULT_MINI_PROVIDER = '[^']*';",
                f"export const DEFAULT_MINI_PROVIDER = '{provider}';",
            ),
        ]
        for pattern, repl in pairs:
            text, count = re.subn(pattern, repl, text, count=1)
            if count != 1:
                raise SystemExit(f"[default_model] regex failed for {pattern} in {rel}")
        ctx.write(rel, text)
        changed = True
    return changed
