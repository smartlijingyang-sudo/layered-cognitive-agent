"""Patch: office preview for private artifact URLs is download, not Office Online."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="office_preview_local",
    description="Local Office files download instead of officeapps.live.com",
    files=("src/features/FileViewer/index.tsx",),
    risk="low",
    category="ui",
    depends_on=(),
    why="Office Online must fetch src on the public internet; /files and localhost 404",
    technical_detail=(
        "MSDocViewer embeds view.officeapps.live.com. Private LCA artifacts are "
        "not reachable, so FileViewer routes them to NotSupport (download)."
    ),
    verify_file="src/features/FileViewer/index.tsx",
    verify_marker="LCA: officeapps cannot fetch private /files or localhost URLs",
)

_HELPER_NEEDLE = """};

/**
 * Preview any file type.
 */
const FileViewer = memo<FileViewerProps>"""

_HELPER_INSERT = """};

const isPublicOfficePreviewUrl = (value: string | null | undefined): boolean => {
  if (!value) return false;
  try {
    const parsed = new URL(value, 'http://lca.invalid');
    if (parsed.protocol !== 'https:') return false;
    const host = parsed.hostname.toLowerCase();
    if (host === 'localhost' || host === '127.0.0.1' || host.endsWith('.local')) return false;
    return true;
  } catch {
    return false;
  }
};

/**
 * Preview any file type.
 */
const FileViewer = memo<FileViewerProps>"""

_NEEDLE = """  // Microsoft Office documents - check before code files to avoid false matches
  // (e.g., 'doc' contains 'c' which would match CODE_EXTENSIONS)
  if (matchesFileType(fileType, name, MSDOC_EXTENSIONS, MSDOC_MIME_TYPES)) {
    return <MSDocViewer fileId={id} url={url} />;
  }
"""

_INSERT = """  // Microsoft Office documents - check before code files to avoid false matches
  // (e.g., 'doc' contains 'c' which would match CODE_EXTENSIONS)
  /* LCA: officeapps cannot fetch private /files or localhost URLs */
  if (matchesFileType(fileType, name, MSDOC_EXTENSIONS, MSDOC_MIME_TYPES)) {
    if (!isPublicOfficePreviewUrl(url)) {
      return <NotSupport fileName={name} style={style} url={url} />;
    }
    return <MSDocViewer fileId={id} url={url} />;
  }
"""


def apply(ctx: PatchContext) -> bool:
    rel = "src/features/FileViewer/index.tsx"
    if ctx.has_marker(rel, "LCA: officeapps cannot fetch private /files or localhost URLs"):
        return False
    text = ctx.read(rel)
    if _HELPER_NEEDLE not in text:
        raise SystemExit("[office_preview_local] FileViewer helper anchor not found")
    if _NEEDLE not in text:
        raise SystemExit("[office_preview_local] MSDoc branch not found")
    text = text.replace(_HELPER_NEEDLE, _HELPER_INSERT, 1)
    ctx.write(rel, text.replace(_NEEDLE, _INSERT, 1))
    return True
