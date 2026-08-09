/**
 * LobeHub-style file preview surface: image / markdown / html / text in a modal.
 * Loads body via `/files/{id}?preview=1` when needed.
 */

import { useEffect, useState } from "react";
import { Download, ExternalLink, X } from "lucide-react";
import type { GeneratedFile } from "../../domain/generated-file";
import { fileIconKind } from "../../lib/file-mime-icon";
import { fileDownloadUrl, filePreviewUrl } from "../../lib/file-preview-url";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import { focusRing, mutedText } from "../../lib/ui";
import { MarkdownContent } from "./MarkdownContent";

export function FilePreviewDialog({
  file,
  open,
  onClose,
}: {
  readonly file: GeneratedFile | null;
  readonly open: boolean;
  readonly onClose: () => void;
}) {
  const [textBody, setTextBody] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const kind = file ? fileIconKind(file.mimeType, file.name) : "file";
  const previewSrc = filePreviewUrl(file?.url);
  const downloadHref = fileDownloadUrl(file?.url);
  const needsTextFetch =
    kind === "text" || kind === "code" || kind === "table" || file?.mimeType.toLowerCase().includes("markdown");

  useEffect(() => {
    if (!open || !file) {
      setTextBody(null);
      setLoadError(null);
      setLoading(false);
      return;
    }
    if (!needsTextFetch || !previewSrc) {
      setTextBody(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void fetch(previewSrc)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((text) => {
        if (!cancelled) {
          setTextBody(text);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "加载失败");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, file, needsTextFetch, previewSrc]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !file) return null;

  const isMd =
    kind === "text" &&
    (file.name.toLowerCase().endsWith(".md") ||
      file.name.toLowerCase().endsWith(".markdown") ||
      file.mimeType.toLowerCase().includes("markdown"));

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 sm:p-8"
      role="dialog"
      aria-modal="true"
      aria-label={`预览 ${file.name}`}
      data-testid="file-preview-dialog"
    >
      <button
        type="button"
        className="absolute inset-0 border-0 bg-black/55 backdrop-blur-[2px]"
        aria-label="关闭预览"
        onClick={onClose}
      />
      <div
        className={cn(
          "relative z-[1] flex max-h-[min(90vh,880px)] w-full max-w-3xl flex-col overflow-hidden",
          "rounded-[var(--radius-xl)] border border-[var(--border)] bg-[var(--surface)] shadow-2xl",
        )}
      >
        <header className="flex shrink-0 items-center gap-3 border-b border-[var(--border)] px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="m-0 truncate text-sm font-semibold text-[var(--text)]">{file.name}</h2>
            <p className={cn("m-0 mt-0.5 truncate text-xs", mutedText)}>{file.mimeType}</p>
          </div>
          {downloadHref ? (
            <a
              href={downloadHref}
              download={file.name}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1.5 text-xs font-medium",
                "text-[var(--accent)] hover:bg-[var(--fill-hover)]",
                focusRing,
              )}
            >
              <LobeIcon icon={Download} size="sm" />
              下载
            </a>
          ) : null}
          {previewSrc && kind === "html" ? (
            <a
              href={previewSrc}
              target="_blank"
              rel="noreferrer"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] px-2 py-1.5 text-xs",
                mutedText,
                "hover:bg-[var(--fill-hover)]",
                focusRing,
              )}
            >
              <LobeIcon icon={ExternalLink} size="sm" />
              新窗口
            </a>
          ) : null}
          <button
            type="button"
            className={cn(
              "inline-flex size-8 items-center justify-center rounded-[var(--radius-sm)]",
              "text-[var(--text-muted)] hover:bg-[var(--fill-hover)]",
              focusRing,
            )}
            onClick={onClose}
            aria-label="关闭"
          >
            <LobeIcon icon={X} size="md" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-auto bg-[var(--chat-bg)] p-4">
          {kind === "image" && previewSrc ? (
            <img
              src={previewSrc}
              alt={file.name}
              className="mx-auto max-h-[min(70vh,720px)] max-w-full rounded-[var(--radius-md)] object-contain"
              data-testid="file-preview-image"
            />
          ) : null}

          {kind === "html" ? (
            file.previewHtml ? (
              <iframe
                title={file.name}
                className="h-[min(70vh,640px)] w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-white"
                sandbox="allow-scripts"
                srcDoc={file.previewHtml}
                data-testid="file-preview-html"
              />
            ) : previewSrc ? (
              <iframe
                title={file.name}
                className="h-[min(70vh,640px)] w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-white"
                sandbox="allow-scripts"
                src={previewSrc}
                data-testid="file-preview-html"
              />
            ) : (
              <p className={cn("m-0 text-sm", mutedText)}>无法预览：缺少 URL</p>
            )
          ) : null}

          {needsTextFetch ? (
            loading ? (
              <p className={cn("m-0 text-sm", mutedText)}>加载中…</p>
            ) : loadError ? (
              <p className="m-0 text-sm text-[var(--color-danger)]">加载失败：{loadError}</p>
            ) : textBody != null ? (
              isMd ? (
                <div
                  className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4"
                  data-testid="file-preview-markdown"
                >
                  <MarkdownContent text={textBody} />
                </div>
              ) : (
                <pre
                  className="m-0 overflow-x-auto rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--code-bg)] p-4 text-[0.8125rem] leading-relaxed text-[var(--code-fg)]"
                  data-testid="file-preview-text"
                >
                  {textBody}
                </pre>
              )
            ) : (
              <p className={cn("m-0 text-sm", mutedText)}>暂无内容</p>
            )
          ) : null}

          {kind !== "image" && kind !== "html" && !needsTextFetch ? (
            <p className={cn("m-0 text-sm", mutedText)}>
              此类型暂不支持内嵌预览，请下载后查看。
              {downloadHref ? (
                <>
                  {" "}
                  <a href={downloadHref} download={file.name} className="text-[var(--accent)] underline">
                    下载文件
                  </a>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
