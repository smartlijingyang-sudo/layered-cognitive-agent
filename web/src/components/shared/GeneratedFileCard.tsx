import {
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Download,
  ExternalLink,
} from "lucide-react";
import type { GeneratedFile } from "../../domain/generated-file";
import { fileIconKind, formatByteSize } from "../../lib/file-mime-icon";
import { cn } from "../../lib/cn";
import { focusRing, mutedText } from "../../lib/ui";

const ICON_BY_KIND = {
  image: FileImage,
  pdf: FileText,
  code: FileCode,
  table: FileSpreadsheet,
  text: FileText,
  archive: FileArchive,
  html: FileCode,
  audio: FileAudio,
  video: FileVideo,
  file: File,
} as const;

export function GeneratedFileCard({ file }: { readonly file: GeneratedFile }) {
  const kind = fileIconKind(file.mimeType, file.name);
  const Icon = ICON_BY_KIND[kind];
  const sizeLabel = formatByteSize(file.sizeBytes);
  const canPreview =
    Boolean(file.previewable) && Boolean(file.previewHtml || file.url);
  const canDownload = Boolean(file.url);

  return (
    <article
      className={cn(
        "min-w-[16rem] max-w-sm overflow-hidden rounded-[var(--radius-lg)]",
        "border border-border bg-surface shadow-sm",
      )}
      data-testid="generated-file-card"
    >
      <div className="flex items-start gap-3 p-3.5">
        <div
          className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-accent/10 text-accent"
          aria-hidden
        >
          <Icon size={18} strokeWidth={1.75} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="m-0 truncate text-sm font-medium text-text" title={file.name}>
            {file.name}
          </h3>
          <p className={cn("m-0 mt-0.5 text-xs", mutedText)}>
            {file.mimeType}
            {sizeLabel ? ` · ${sizeLabel}` : ""}
          </p>
        </div>
      </div>

      {canPreview ? (
        <div className="border-t border-border px-3 pb-3 pt-2">
          {file.previewHtml ? (
            <iframe
              title={`预览 ${file.name}`}
              className="h-24 w-full rounded-[var(--radius-sm)] border border-border bg-bg"
              sandbox="allow-scripts"
              srcDoc={file.previewHtml}
              data-testid="generated-file-preview"
            />
          ) : (
            <iframe
              title={`预览 ${file.name}`}
              className="h-24 w-full rounded-[var(--radius-sm)] border border-border bg-bg"
              sandbox="allow-scripts"
              src={file.url}
              data-testid="generated-file-preview"
            />
          )}
        </div>
      ) : null}

      <div className="flex items-center gap-2 border-t border-border bg-[color-mix(in_srgb,var(--surface-elevated)_80%,transparent)] px-3 py-2">
        {canDownload ? (
          <a
            href={file.url}
            download={file.name}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1 text-xs font-medium text-accent hover:underline",
              focusRing,
            )}
            data-testid="generated-file-download"
          >
            <Download size={13} />
            下载
          </a>
        ) : (
          <span className={cn("inline-flex items-center gap-1.5 text-xs", mutedText)}>
            <ExternalLink size={13} />
            暂无下载地址
          </span>
        )}
      </div>
    </article>
  );
}

export function GeneratedFileList({
  files,
}: {
  readonly files: readonly GeneratedFile[];
}) {
  if (!files.length) return null;
  return (
    <div
      className="mt-3 flex flex-wrap gap-2.5"
      data-testid="generated-file-list"
      aria-label="生成文件"
    >
      {files.map((file) => (
        <GeneratedFileCard key={`${file.name}-${file.mimeType}-${file.url ?? ""}`} file={file} />
      ))}
    </div>
  );
}
