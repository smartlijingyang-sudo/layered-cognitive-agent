"""Patch: openai_guard — LCA virtual models bypass Responses API."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="openai_guard",
    description="LCA virtual models bypass Responses API",
    files=("packages/model-runtime/src/providers/openai/index.ts",),
    risk="medium",
    category="provider",
    depends_on=(),
    why="LCA virtual models (solo/team/auto) must use chat/completions, not OpenAI Responses API",
    technical_detail=(
        "Add isLcaGatewayModel check: if model in ['solo','team','auto'], "
        "force chat/completions path regardless of model capabilities."
    ),
    verify_file="packages/model-runtime/src/providers/openai/index.ts",
    verify_marker="LCA: solo/team always chat/completions",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "packages/model-runtime/src/providers/openai/index.ts"
    if ctx.has_marker(rel, "LCA: solo/team always chat/completions"):
        return False
    text = ctx.read(rel)
    needle = "      if (isResponsesAPIModel(model) || enabledSearch) {"
    if needle not in text:
        raise SystemExit("[openai_guard] anchor not found")
    marker = "/* LCA: solo/team always chat/completions */"
    replacement = (
        "      const isLcaGatewayModel = ['solo', 'team', 'auto'].includes(model);\n"
        f"      {marker}\n"
        "      if (!isLcaGatewayModel && (isResponsesAPIModel(model) || enabledSearch)) {"
    )
    ctx.write(rel, text.replace(needle, replacement, 1))
    return True
