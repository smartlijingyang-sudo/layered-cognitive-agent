"""Patch: sandbox_generated_files — Show harvested sandbox files on executeCode cards."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="sandbox_generated_files",
    description="Show harvested sandbox files on executeCode cards",
    files=("packages/builtin-tool-cloud-sandbox/src/client/Render/ExecuteCode/index.tsx",),
    risk="medium",
    category="ui",
    depends_on=(),
    why="Sandbox code execution produces files that should be visible in the UI",
    technical_detail="Add GeneratedFilesStrip component to render file download links from tool state.",
    verify_file="packages/builtin-tool-cloud-sandbox/src/client/Render/ExecuteCode/index.tsx",
    verify_marker="GeneratedFilesStrip",
)


def apply(ctx: PatchContext) -> bool:
    """Return True if applied, False if already applied (skipped)."""
    rel = "packages/builtin-tool-cloud-sandbox/src/client/Render/ExecuteCode/index.tsx"
    if ctx.has_marker(rel, "GeneratedFilesStrip"):
        return False
    text = ctx.read(rel)
    text = text.replace(
        "import { Block, Flexbox, Highlighter } from '@lobehub/ui';",
        "import { Block, Flexbox, Highlighter, Text } from '@lobehub/ui';\nimport { Button } from 'antd';",
        1,
    )
    insert = """
interface GeneratedFilePart {
  attachmentId?: string;
  mimeType?: string;
  name?: string;
  previewable?: boolean;
  url?: string;
}

const GeneratedFilesStrip = memo<{ files?: GeneratedFilePart[] }>(({ files }) => {
  if (!files?.length) return null;
  return (
    <Flexbox gap={4}>
      <Text style={{ fontSize: 12, opacity: 0.65 }}>Generated files</Text>
      <Flexbox gap={4} horizontal wrap>
        {files.map((file) => {
          const label = file.name || 'file';
          const href = file.url;
          if (!href) return null;
          return (
            <Button
              href={href}
              key={`${label}-${href}`}
              rel="noopener noreferrer"
              size="small"
              target="_blank"
              type={file.previewable ? 'primary' : 'default'}
            >
              {label}
            </Button>
          );
        })}
      </Flexbox>
    </Flexbox>
  );
});

GeneratedFilesStrip.displayName = 'GeneratedFilesStrip';
"""
    text = text.replace(
        "const styles = createStaticStyles(({ css }) => ({",
        insert + "\nconst styles = createStaticStyles(({ css }) => ({",
        1,
    )
    text = text.replace(
        "          {pluginState?.stderr && (\n            <Highlighter wrap language={'text'} showLanguage={false} variant={'filled'}>\n              {pluginState.stderr}\n            </Highlighter>\n          )}\n        </Block>",
        "          {pluginState?.stderr && (\n            <Highlighter wrap language={'text'} showLanguage={false} variant={'filled'}>\n              {pluginState.stderr}\n            </Highlighter>\n          )}\n          <GeneratedFilesStrip files={(pluginState as { files?: GeneratedFilePart[] })?.files} />\n        </Block>",
        1,
    )
    ctx.write(rel, text)
    return True
