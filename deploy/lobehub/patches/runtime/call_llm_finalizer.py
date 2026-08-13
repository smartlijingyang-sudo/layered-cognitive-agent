"""Patch: call_llm_finalizer — Skip client tool loop when lcaClosedLoop."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="call_llm_finalizer",
    description="Skip client tool loop when lcaClosedLoop",
    files=("packages/agent-runtime/src/executors/callLlmFinalizer.ts",),
    risk="high",
    category="runtime",
    depends_on=("journal_transport",),
    why="Prevent LobeHub's client-side tool loop from duplicating LCA's server-side execution",
    technical_detail=(
        "Change hasToolsCalling condition: !output.lcaClosedLoop && output.toolsCalling.length > 0. "
        "When LCA handles tools server-side, the client must not re-invoke them."
    ),
    verify_file="packages/agent-runtime/src/executors/callLlmFinalizer.ts",
    verify_marker="output.lcaClosedLoop",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "packages/agent-runtime/src/executors/callLlmFinalizer.ts"
    if ctx.has_marker(rel, "output.lcaClosedLoop"):
        return False
    text = ctx.read(rel)
    repl = "hasToolsCalling: !output.lcaClosedLoop && output.toolsCalling.length > 0,"
    text = text.replace(
        "hasToolsCalling: output.toolsCalling.length > 0,",
        repl,
    )
    if repl not in text:
        raise SystemExit("[call_llm_finalizer] hasToolsCalling anchor not found")
    ctx.write(rel, text)
    return True
