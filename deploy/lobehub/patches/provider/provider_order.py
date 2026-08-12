"""Patch: provider_order — Move OpenAI provider to first position."""

from __future__ import annotations

import re

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="provider_order",
    description="Move OpenAI provider to first position",
    files=("packages/model-bank/src/modelProviders/index.ts",),
    risk="low",
    category="provider",
    depends_on=(),
    why="OpenAI provider (LCA gateway) should be the first/default option",
    technical_detail="Reorder DEFAULT_MODEL_PROVIDER_LIST to put OpenAIProvider first.",
    verify_file="packages/model-bank/src/modelProviders/index.ts",
    verify_marker="/* LCA: OpenAI first */",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "packages/model-bank/src/modelProviders/index.ts"
    if ctx.has_marker(rel, "/* LCA: OpenAI first */"):
        return False
    text = ctx.read(rel)
    needle = "  ...(ENABLE_BUSINESS_FEATURES ? [LobeHubProvider] : []),\n"
    if needle not in text:
        raise SystemExit("[provider_order] LobeHub spread anchor not found")
    text = re.sub(r"\n  OpenAIProvider,\n", "\n", text, count=1)
    text = text.replace(needle, needle + "  OpenAIProvider, /* LCA: OpenAI first */\n", 1)
    ctx.write(rel, text)
    return True
