"""Patch: ExecuteCode render shows LCA generated files with download links.

Upstream ExecuteCode render only shows code/stdout/stderr. LCA's
lcaArtifacts.toFileList() also emits ``files`` in plugin_state; surface
them as clickable cards so users can preview or download sandbox output.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_TARGET_REL = "packages/builtin-tool-cloud-sandbox/src/client/Render/ExecuteCode/index.tsx"
_SOURCE_NAME = "ExecuteCodeRender.tsx"

meta = PatchMeta(
    name="execute_code_attachments",
    description="ExecuteCode render displays LCA generated files as download cards",
    files=(_TARGET_REL,),
    risk="low",
    category="ui",
    depends_on=(),
    why=(
        "LCA's lcaArtifacts populates pluginState.files with /files/* URLs; "
        "without a render hook users see the code but cannot retrieve outputs"
    ),
    technical_detail=(
        "Whole-file copy patch; LCA version adds GeneratedFilesStrip reading "
        "pluginState.files and rendering LcaGeneratedFileCard per entry."
    ),
    verify_file=_TARGET_REL,
    verify_marker="GeneratedFilesStrip",
)


def apply(ctx: PatchContext) -> bool:
    source = _HERE / _SOURCE_NAME
    if not source.is_file():
        raise SystemExit(f"[execute_code_attachments] missing patch source: {source}")
    return ctx.write_if_changed(_TARGET_REL, source.read_text(encoding="utf-8"))
