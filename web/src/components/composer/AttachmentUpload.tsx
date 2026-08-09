import { useCallback, useId, useRef, useState } from "react";
import { Paperclip, X, File as FileIcon, AlertCircle } from "lucide-react";
import type { LocalAttachment } from "../../domain/generated-file";
import { formatByteSize } from "../../lib/file-mime-icon";
import {
  FileApiNotAvailableError,
  uploadAttachment,
} from "../../api/files";
import { cn } from "../../lib/cn";
import { focusRing, mutedText } from "../../lib/ui";

function newLocalId(): string {
  return `att-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function fileToLocal(file: File): LocalAttachment {
  return {
    id: newLocalId(),
    name: file.name,
    mimeType: file.type || "application/octet-stream",
    sizeBytes: file.size,
    status: "local",
    file,
  };
}

export function AttachmentUpload({
  attachments,
  onChange,
  conversationId,
  disabled = false,
  /** When true and conversationId is set, attempt real upload via api/files. */
  autoUpload = false,
  /** Icon-only control for composer action bar (chips rendered elsewhere). */
  compact = false,
}: {
  readonly attachments: readonly LocalAttachment[];
  readonly onChange: (next: readonly LocalAttachment[]) => void;
  readonly conversationId?: string;
  readonly disabled?: boolean;
  readonly autoUpload?: boolean;
  readonly compact?: boolean;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const addFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList);
      if (!files.length) return;

      const added = files.map(fileToLocal);
      let next: LocalAttachment[] = [...attachments, ...added];
      onChange(next);

      if (!autoUpload || !conversationId) {
        return;
      }

      for (const att of added) {
        if (!att.file) continue;
        next = next.map((a) =>
          a.id === att.id ? { ...a, status: "uploading" as const } : a,
        );
        onChange(next);

        try {
          const ref = await uploadAttachment(conversationId, att.file);
          next = next.map((a) =>
            a.id === att.id
              ? { ...a, status: "uploaded" as const, ref, error: undefined }
              : a,
          );
          onChange(next);
        } catch (err) {
          const message =
            err instanceof FileApiNotAvailableError
              ? "后端尚未开放上传，已保留在本地"
              : err instanceof Error
                ? err.message
                : "上传失败";
          next = next.map((a) =>
            a.id === att.id
              ? {
                  ...a,
                  // keep usable as local attachment even when upload fails
                  status: "error" as const,
                  error: message,
                }
              : a,
          );
          onChange(next);
        }
      }
    },
    [attachments, autoUpload, conversationId, onChange],
  );

  const remove = useCallback(
    (id: string) => {
      onChange(attachments.filter((a) => a.id !== id));
    },
    [attachments, onChange],
  );

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(false);
      if (disabled) return;
      if (event.dataTransfer.files?.length) {
        void addFiles(event.dataTransfer.files);
      }
    },
    [addFiles, disabled],
  );

  if (compact) {
    return (
      <div className="relative" data-testid="attachment-upload">
        <label
          htmlFor={inputId}
          className={cn(
            "inline-flex size-8 cursor-pointer items-center justify-center rounded-[var(--radius-md)]",
            "text-[var(--text-muted)] hover:bg-[var(--fill-hover)] hover:text-[var(--text)]",
            disabled && "pointer-events-none opacity-50",
            focusRing,
          )}
          title="添加附件"
        >
          <Paperclip size={15} />
          {attachments.length > 0 ? (
            <span className="absolute -top-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full bg-[var(--accent)] text-[9px] font-medium text-[var(--accent-fg)]">
              {attachments.length}
            </span>
          ) : null}
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          className="sr-only"
          multiple
          disabled={disabled}
          onChange={(e) => {
            if (e.target.files?.length) void addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
    );
  }

  return (
    <div className="grid gap-2" data-testid="attachment-upload">
      {attachments.length > 0 ? (
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label="待发送附件">
          {attachments.map((att) => (
            <li
              key={att.id}
              className={cn(
                "flex max-w-full items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-xs",
              )}
              data-testid="attachment-chip"
            >
              <FileIcon size={12} className="shrink-0 text-[var(--text-muted)]" aria-hidden />
              <span className="max-w-[10rem] truncate text-[var(--text)]" title={att.name}>
                {att.name}
              </span>
              <span className={mutedText}>{formatByteSize(att.sizeBytes)}</span>
              {att.status === "error" ? (
                <span
                  className="inline-flex items-center gap-0.5 text-[var(--color-danger)]"
                  title={att.error}
                >
                  <AlertCircle size={12} />
                </span>
              ) : null}
              <button
                type="button"
                className={cn(
                  "inline-flex size-5 items-center justify-center rounded-full text-[var(--text-muted)] hover:bg-[var(--fill-hover)] hover:text-[var(--text)]",
                  focusRing,
                )}
                onClick={() => remove(att.id)}
                aria-label={`移除 ${att.name}`}
                disabled={disabled}
                data-testid="attachment-remove"
              >
                <X size={12} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div
        className={cn(
          "flex items-center gap-2 rounded-[var(--radius-md)] border border-dashed px-3 py-2 transition-colors",
          dragging
            ? "border-[var(--accent)] bg-[var(--fill-hover)]"
            : "border-[var(--border)] bg-transparent",
          disabled && "pointer-events-none opacity-50",
        )}
        onDragEnter={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragging(false);
        }}
        onDrop={onDrop}
        data-testid="attachment-dropzone"
      >
        <label
          htmlFor={inputId}
          className={cn(
            "inline-flex cursor-pointer items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text)]",
            focusRing,
            "rounded-sm",
          )}
        >
          <Paperclip size={14} />
          添加附件
        </label>
        <span className={cn("text-[11px]", mutedText)}>或拖拽到此处</span>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          className="sr-only"
          multiple
          disabled={disabled}
          onChange={(e) => {
            if (e.target.files?.length) {
              void addFiles(e.target.files);
              e.target.value = "";
            }
          }}
          data-testid="attachment-input"
        />
      </div>
    </div>
  );
}
