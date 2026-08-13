"""Patch: FileListViewer opens gateway /files URLs instead of the LobeHub file store."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="file_list_gateway_preview",
    description="Native file cards preview /files artifacts via URL",
    files=("src/features/Conversation/Messages/User/components/FileListViewer/Item.tsx",),
    risk="low",
    category="ui",
    depends_on=(),
    why="Group FileListViewer calls openFilePreview({ fileId }); LCA artifacts live at /files, not the LobeHub file store",
    technical_detail=(
        "Clicking a card whose url is /files/* or http(s) opens that URL. "
        "LobeHub file-store ids keep the portal preview path."
    ),
    verify_file="src/features/Conversation/Messages/User/components/FileListViewer/Item.tsx",
    verify_marker="LCA: gateway /files preview",
)

_NEEDLE = """const FileItem = memo<ChatFileItem>(({ id, fileType, size, name, inaccessible }) => {
  const openFilePreview = useChatStore((s) => s.openFilePreview);

  if (inaccessible) return <InaccessibleFileItem />;

  return (
    <Block
      clickable
      horizontal
      align={'center'}
      gap={12}
      key={id}
      paddingBlock={8}
      paddingInline={'12px 16px'}
      variant={'outlined'}
      onClick={() => {
        openFilePreview({ fileId: id });
      }}
    >
"""

_INSERT = """const FileItem = memo<ChatFileItem>(({ id, fileType, size, name, inaccessible, url }) => {
  const openFilePreview = useChatStore((s) => s.openFilePreview);

  if (inaccessible) return <InaccessibleFileItem />;

  return (
    <Block
      clickable
      horizontal
      align={'center'}
      gap={12}
      key={id}
      paddingBlock={8}
      paddingInline={'12px 16px'}
      variant={'outlined'}
      onClick={() => {
        /* LCA: gateway /files preview */
        if (url && (/^\\/files\\//.test(url) || /^https?:\\/\\//.test(url))) {
          window.open(url, '_blank', 'noopener,noreferrer');
          return;
        }
        openFilePreview({ fileId: id });
      }}
    >
"""


def apply(ctx: PatchContext) -> bool:
    rel = "src/features/Conversation/Messages/User/components/FileListViewer/Item.tsx"
    if ctx.has_marker(rel, "LCA: gateway /files preview"):
        return False
    text = ctx.read(rel)
    if _NEEDLE not in text:
        raise SystemExit("[file_list_gateway_preview] FileListViewer Item onClick anchor not found")
    ctx.write(rel, text.replace(_NEEDLE, _INSERT, 1))
    return True
