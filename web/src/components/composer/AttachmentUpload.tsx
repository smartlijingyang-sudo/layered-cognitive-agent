/**
 * LobeHub ChatInput attachment UI alignment:
 *
 * - compact: circular Paperclip action (action bar)
 * - list: horizontal cards 180×64 (FileItem) for pending/uploading
 *         + compact tags (ContextItem) once ready — both with real thumbs
 */
import { useCallback, useEffect, useId, useMemo, useRef } from "react";
import {
  AlertCircle,
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Loader2,
  Trash2,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { LocalAttachment } from "../../domain/generated-file";
import { fileIconKind, formatByteSize } from "../../lib/file-mime-icon";
import {
  FileApiNotAvailableError,
  uploadAttachment,
} from "../../api/files";
import { cn } from "../../lib/cn";
import { ICON_STROKE, LobeIcon } from "../../lib/icons";
import { focusRing } from "../../lib/ui";
import { PlusActionMenu } from "./PlusActionMenu";
import type { ComposerMenuPlacement } from "./menu-position";

const KIND_ICON: Record<string, LucideIcon> = {
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
};

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

function basename(name: string): string {
  const i = name.lastIndexOf(".");
  if (i <= 0) return name;
  return name.slice(0, i);
}

function useObjectUrl(file: File | undefined): string | null {
  const url = useMemo(() => {
    if (!file) return null;
    // jsdom / older env may lack createObjectURL
    if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
      return null;
    }
    try {
      return URL.createObjectURL(file);
    } catch {
      return null;
    }
  }, [file]);

  useEffect(() => {
    return () => {
      if (url && typeof URL.revokeObjectURL === "function") {
        URL.revokeObjectURL(url);
      }
    };
  }, [url]);

  return url;
}

/** 64×64 preview zone — image cover / video / large file icon (LobeHub FileItem Content). */
function FilePreviewThumb({
  att,
  large = false,
}: {
  readonly att: LocalAttachment;
  readonly large?: boolean;
}) {
  const url = useObjectUrl(att.file);
  const kind = fileIconKind(att.mimeType, att.name);
  const Icon = KIND_ICON[kind] ?? File;
  const isImage = att.mimeType.startsWith("image/");
  const isVideo = att.mimeType.startsWith("video/");

  if (isImage && url) {
    return (
      <img
        src={url}
        alt=""
        className="size-full object-cover"
        style={{ borderRadius: large ? 6 : 4 }}
      />
    );
  }
  if (isVideo && url) {
    return (
      <video
        src={url}
        className="size-full object-cover"
        style={{ borderRadius: large ? 6 : 4 }}
        muted
        playsInline
      />
    );
  }
  return (
    <LobeIcon
      icon={Icon}
      size={large ? 40 : "xs"}
      className="text-[var(--text-muted)]"
    />
  );
}

/** LobeHub FileItem — 180×64 outlined card (uploading / local pending). */
function FileItemCard({
  att,
  disabled,
  onRemove,
}: {
  readonly att: LocalAttachment;
  readonly disabled: boolean;
  readonly onRemove: () => void;
}) {
  const uploading = att.status === "uploading";
  const errored = att.status === "error";
  const sizeLabel = formatByteSize(att.sizeBytes);

  return (
    <li
      className={cn(
        "lobe-file-item relative flex h-16 w-[180px] shrink-0 items-center overflow-hidden",
        "rounded-lg border border-[var(--border)] bg-[var(--surface)]",
        "shadow-[0_0_0_0.5px_var(--border-subtle)_inset,var(--shadow-card)]",
      )}
      data-testid="attachment-chip"
      title={att.error ?? att.name}
    >
      <div className="flex size-16 shrink-0 items-center justify-center p-1">
        <div className="relative flex size-14 items-center justify-center overflow-hidden rounded-md bg-[var(--fill-secondary)]">
          <FilePreviewThumb att={att} large />
          {uploading ? (
            <span className="absolute inset-0 flex items-center justify-center bg-black/45">
              <Loader2 size={18} strokeWidth={ICON_STROKE} className="animate-spin text-white" />
            </span>
          ) : null}
        </div>
      </div>
      <div className="flex min-w-0 flex-1 flex-col justify-center gap-1 py-1 pr-2">
        <span
          className="truncate text-xs leading-[1.25] text-[var(--text)]"
          style={{ maxWidth: 88 }}
          title={att.name}
        >
          {att.name}
        </span>
        <span className="truncate text-xs leading-none text-[var(--text-muted)]">
          {errored
            ? att.error || "失败"
            : uploading
              ? "上传中…"
              : sizeLabel || ""}
        </span>
      </div>
      <button
        type="button"
        className={cn(
          "absolute -top-1 -right-1 z-10 inline-flex size-6 items-center justify-center",
          "rounded-[5px] border border-[var(--border-subtle)] bg-[var(--surface-elevated)]",
          "text-[var(--color-danger)] shadow-[var(--shadow-card)]",
          "hover:bg-[color-mix(in_srgb,var(--color-danger)_10%,var(--surface-elevated))]",
          focusRing,
        )}
        onClick={onRemove}
        aria-label={`移除 ${att.name}`}
        disabled={disabled}
        data-testid="attachment-remove"
      >
        <LobeIcon icon={Trash2} size="xs" />
      </button>
    </li>
  );
}

/** LobeHub ContextItem Tag — compact after ready. */
function ContextTag({
  att,
  disabled,
  onRemove,
}: {
  readonly att: LocalAttachment;
  readonly disabled: boolean;
  readonly onRemove: () => void;
}) {
  const errored = att.status === "error";
  return (
    <li
      className={cn(
        "lobe-att-chip inline-flex h-7 max-w-[12rem] items-center gap-1.5",
        "rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--fill-secondary)]",
        "py-0 pr-1 pl-1.5 text-sm leading-none",
        errored && "border-[var(--color-danger)]/35",
      )}
      data-testid="attachment-chip"
      title={att.error ?? att.name}
    >
      <span className="lobe-att-thumb relative inline-flex size-[18px] shrink-0 items-center justify-center overflow-hidden rounded-[4px]">
        <FilePreviewThumb att={att} />
      </span>
      <span className="min-w-0 flex-1 truncate text-sm leading-[18px] text-[var(--text)]">
        {basename(att.name)}
      </span>
      {errored ? (
        <LobeIcon icon={AlertCircle} size="xs" className="text-[var(--color-danger)]" />
      ) : null}
      <button
        type="button"
        className={cn(
          "inline-flex size-5 shrink-0 items-center justify-center rounded-full",
          "text-[var(--text-faint)] hover:bg-[color-mix(in_srgb,var(--color-danger)_12%,transparent)] hover:text-[var(--color-danger)]",
          focusRing,
        )}
        onClick={onRemove}
        aria-label={`移除 ${att.name}`}
        disabled={disabled}
        data-testid="attachment-remove"
      >
        <LobeIcon icon={X} size="xs" />
      </button>
    </li>
  );
}

export function AttachmentUpload({
  attachments,
  onChange,
  conversationId,
  disabled = false,
  autoUpload = false,
  compact = false,
  menuPlacement = "topLeft",
  onDropFiles,
}: {
  readonly attachments: readonly LocalAttachment[];
  readonly onChange: (next: readonly LocalAttachment[]) => void;
  readonly conversationId?: string;
  readonly disabled?: boolean;
  readonly autoUpload?: boolean;
  readonly compact?: boolean;
  readonly menuPlacement?: ComposerMenuPlacement;
  /** Optional external drop handler (Composer drag-drop). */
  readonly onDropFiles?: (files: FileList) => void;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList);
      if (!files.length) return;

      const added = files.map(fileToLocal);
      let next: LocalAttachment[] = [...attachments, ...added];
      onChange(next);

      if (!autoUpload || !conversationId) return;

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
              ? { ...a, status: "error" as const, error: message }
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

  const fileInput = (
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
      data-testid="attachment-input"
    />
  );

  const ingestFiles = useCallback(
    (fileList: FileList | File[]) => {
      void addFiles(fileList);
    },
    [addFiles],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (disabled || !e.dataTransfer.files?.length) return;
      if (onDropFiles) {
        onDropFiles(e.dataTransfer.files);
      } else {
        ingestFiles(e.dataTransfer.files);
      }
    },
    [disabled, ingestFiles, onDropFiles],
  );

  const dropHandlers = disabled
    ? {}
    : {
        onDragOver: (e: React.DragEvent) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        },
        onDrop: handleDrop,
      };

  if (compact) {
    return (
      <span className="inline-flex items-center" data-testid="attachment-upload" {...dropHandlers}>
        <PlusActionMenu
          disabled={disabled}
          attachments={attachments}
          onPickFiles={ingestFiles}
          onRemoveAttachment={remove}
          menuPlacement={menuPlacement}
        />
      </span>
    );
  }

  // Split like LobeHub: uploading/error → big FileItem; ready → compact Tag
  const pending = attachments.filter(
    (a) => a.status === "uploading" || a.status === "error" || a.status === "local",
  );
  const ready = attachments.filter((a) => a.status === "uploaded");

  // Without autoUpload, local files stay as cards (user still reviewing before send)
  const showCards = pending.length > 0;
  const showTags = ready.length > 0;

  if (attachments.length === 0) {
    return (
      <div className="hidden" data-testid="attachment-upload">
        {fileInput}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-0" data-testid="attachment-upload" {...dropHandlers}>
      {showCards ? (
        <ul
          className="m-0 flex list-none gap-2 overflow-x-auto p-0 py-2"
          aria-label="待处理附件"
        >
          {pending.map((att) => (
            <FileItemCard
              key={att.id}
              att={att}
              disabled={disabled}
              onRemove={() => remove(att.id)}
            />
          ))}
        </ul>
      ) : null}
      {showTags ? (
        <ul
          className="m-0 flex list-none flex-wrap gap-1 overflow-x-auto p-0 pt-2"
          aria-label="已添加附件"
        >
          {ready.map((att) => (
            <ContextTag
              key={att.id}
              att={att}
              disabled={disabled}
              onRemove={() => remove(att.id)}
            />
          ))}
        </ul>
      ) : null}
      {fileInput}
    </div>
  );
}
