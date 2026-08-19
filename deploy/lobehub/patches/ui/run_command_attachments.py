"""Patch: RunCommand render shows LCA generated files with download links.

Same generated-files pattern as execute_code_attachments; surface
pluginState.files produced by lcaArtifacts so shell pipelines that emit
files can also be retrieved.
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_HERE = Path(__file__).resolve().parent
_TARGET_REL = "packages/shared-tool-ui/src/Render/RunCommand/index.tsx"
_SOURCE_NAME = "RunCommandRender.tsx"

meta = PatchMeta(
    name="run_command_attachments",
    description="RunCommand render displays LCA generated files as download cards",
    files=(_TARGET_REL,),
    risk="low",
    category="ui",
    depends_on=(),
    why=(
        "LCA's lcaArtifacts populates pluginState.files with /files/* URLs; "
        "without a render hook users see the command output but cannot retrieve files"
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
        raise SystemExit(f"[run_command_attachments] missing patch source: {source}")
    return ctx.write_if_changed(_TARGET_REL, source.read_text(encoding="utf-8"))
