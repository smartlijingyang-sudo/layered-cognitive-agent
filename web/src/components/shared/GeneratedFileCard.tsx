import { useState } from "react";
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
  Eye,
} from "lucide-react";
import type { GeneratedFile } from "../../domain/generated-file";
import { fileIconKind, formatByteSize } from "../../lib/file-mime-icon";
import { fileDownloadUrl, filePreviewUrl } from "../../lib/file-preview-url";
import { cn } from "../../lib/cn";
import { focusRing, mutedText } from "../../lib/ui";
import { FilePreviewDialog } from "./FilePreviewDialog";

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

function canOpenPreview(file: GeneratedFile): boolean {
  if (file.previewHtml) return true;
  if (!file.url) return false;
  if (file.previewable) return true;
  const kind = fileIconKind(file.mimeType, file.name);
  return kind === "image" || kind === "html" || kind === "text" || kind === "code" || kind === "table";
}

export function GeneratedFileCard({ file }: { readonly file: GeneratedFile }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const kind = fileIconKind(file.mimeType, file.name);
  const Icon = ICON_BY_KIND[kind];
  const sizeLabel = formatByteSize(file.sizeBytes);
  const downloadHref = fileDownloadUrl(file.url);
  const previewSrc = filePreviewUrl(file.url);
  const openable = canOpenPreview(file);

  const openPreview = () => {
    if (openable) setPreviewOpen(true);
  };

  return (
    <>
      <article
        className={cn(
          "min-w-[15rem] max-w-sm overflow-hidden rounded-[var(--radius-lg)]",
          "border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-card)]",
          "transition-colors hover:border-[var(--text-faint)]",
        )}
        data-testid="generated-file-card"
      >
        {kind === "image" && previewSrc ? (
          <button
            type="button"
            className={cn(
              "block w-full cursor-pointer border-0 bg-[var(--fill-hover)] p-0",
              focusRing,
            )}
            onClick={openPreview}
            aria-label={`预览图片 ${file.name}`}
          >
            <img
              src={previewSrc}
              alt=""
              className="h-32 w-full object-cover"
              data-testid="generated-file-thumb"
            />
          </button>
        ) : null}

        {kind === "html" && openable ? (
          <div className="border-b border-[var(--border)] px-2 pt-2">
            {file.previewHtml ? (
              <iframe
                title={`预览 ${file.name}`}
                className="h-28 w-full rounded-[var(--radius-sm)] border border-[var(--border)] bg-white"
                sandbox="allow-scripts"
                srcDoc={file.previewHtml}
                data-testid="generated-file-preview"
              />
            ) : previewSrc ? (
              <iframe
                title={`预览 ${file.name}`}
                className="h-28 w-full rounded-[var(--radius-sm)] border border-[var(--border)] bg-white"
                sandbox="allow-scripts"
                src={previewSrc}
                data-testid="generated-file-preview"
              />
            ) : null}
          </div>
        ) : null}

        <button
          type="button"
          className={cn(
            "flex w-full cursor-pointer items-start gap-3 border-0 bg-transparent p-3.5 text-left",
            openable ? "hover:bg-[var(--fill-hover)]" : "cursor-default",
            focusRing,
          )}
          onClick={openPreview}
          disabled={!openable}
        >
          <div
            className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--accent-soft)] text-[var(--text)]"
            aria-hidden
          >
            <Icon size={18} strokeWidth={1.75} />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="m-0 truncate text-sm font-medium text-[var(--text)]" title={file.name}>
              {file.name}
            </h3>
            <p className={cn("m-0 mt-0.5 text-xs", mutedText)}>
              {file.mimeType}
              {sizeLabel ? ` · ${sizeLabel}` : ""}
            </p>
          </div>
        </button>

        <div className="flex items-center gap-1 border-t border-[var(--border)] bg-[color-mix(in_srgb,var(--surface-elevated)_80%,transparent)] px-2 py-1.5">
          {openable ? (
            <button
              type="button"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1 text-xs font-medium",
                "text-[var(--accent)] hover:bg-[var(--fill-hover)]",
                focusRing,
              )}
              onClick={openPreview}
              data-testid="generated-file-preview-btn"
            >
              <Eye size={13} />
              预览
            </button>
          ) : null}
          {downloadHref ? (
            <a
              href={downloadHref}
              download={file.name}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1 text-xs font-medium",
                "text-[var(--accent)] hover:bg-[var(--fill-hover)] hover:underline",
                focusRing,
              )}
              data-testid="generated-file-download"
              onClick={(e) => e.stopPropagation()}
            >
              <Download size={13} />
              下载
            </a>
          ) : (
            <span className={cn("inline-flex items-center gap-1.5 px-2 py-1 text-xs", mutedText)}>
              <ExternalLink size={13} />
              暂无下载地址
            </span>
          )}
        </div>
      </article>

      <FilePreviewDialog
        file={file}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
      />
    </>
  );
}

export function GeneratedFileList({
  files,
}: {
  readonly files: readonly GeneratedFile[];
}) {
  if (!files.length) return null;
  // Prefer user-facing products first: images / html / md before stderr logs
  const ranked = [...files].sort((a, b) => productRank(a) - productRank(b));
  return (
    <div
      className="mt-3 flex flex-wrap gap-2.5"
      data-testid="generated-file-list"
      aria-label="生成文件"
    >
      {ranked.map((file) => (
        <GeneratedFileCard
          key={`${file.attachmentId ?? ""}|${file.name}|${file.mimeType}|${file.url ?? ""}`}
          file={file}
        />
      ))}
    </div>
  );
}

function productRank(file: GeneratedFile): number {
  const n = file.name.toLowerCase();
  if (n.endsWith(".log") || n.includes("_stderr") || n.includes("_stdout")) return 90;
  const kind = fileIconKind(file.mimeType, file.name);
  if (kind === "image") return 0;
  if (kind === "html") return 1;
  if (n.endsWith(".md") || file.mimeType.includes("markdown")) return 2;
  if (kind === "text" || kind === "table" || kind === "code") return 3;
  return 50;
}
