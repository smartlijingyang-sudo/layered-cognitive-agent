/**
 * LobeHub Plus/Upload menu row — antd Upload semantics without antd.
 * Icon column is a sibling of the label text (fixed 20px cell) so rows
 * align with the parent「附件」item and attachment checklist rows.
 */
import { useId, useRef, useState, type ReactNode } from "react";
import { cn } from "../../lib/cn";
import { ComposerMenuIcon, composerMenuRowInteractive } from "./composer-menu";

/** Full-row hit target — mirrors LobeHub hotArea inset stretch. */
const HOT_AREA =
  "pointer-events-none absolute inset-0 z-[1] rounded-[inherit] bg-transparent";

export function UploadMenuRow({
  disabled,
  multiple = true,
  accept,
  onFiles,
  onAfterPick,
  icon,
  label,
}: {
  readonly disabled?: boolean;
  readonly multiple?: boolean;
  readonly accept?: string;
  readonly onFiles: (files: FileList) => void;
  readonly onAfterPick?: () => void;
  /** 20px leading icon — kept out of the label flex so columns stay aligned. */
  readonly icon: ReactNode;
  readonly label: string;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const [dragOver, setDragOver] = useState(false);

  const ingest = (files: FileList | null) => {
    if (disabled || !files?.length) return;
    onFiles(files);
    onAfterPick?.();
  };

  return (
    <div
      role="presentation"
      className={cn(
        "relative w-full",
        dragOver &&
          "rounded-[var(--radius-sm)] bg-[color-mix(in_srgb,var(--accent)_10%,var(--surface-elevated))] ring-1 ring-[var(--accent)]",
      )}
      onDragEnter={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (disabled) return;
        dragDepth.current += 1;
        setDragOver(true);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!disabled) e.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        e.stopPropagation();
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        dragDepth.current = 0;
        setDragOver(false);
        ingest(e.dataTransfer.files);
      }}
    >
      <label
        htmlFor={disabled ? undefined : inputId}
        role="menuitem"
        className={cn(
          composerMenuRowInteractive,
          "relative w-full",
          disabled && "cursor-not-allowed opacity-50",
          dragOver && "bg-transparent hover:bg-transparent",
        )}
        data-testid="upload-menu-row"
      >
        <ComposerMenuIcon>{icon}</ComposerMenuIcon>
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {!disabled ? <span className={HOT_AREA} aria-hidden /> : null}
      </label>
      <input
        ref={inputRef}
        id={inputId}
        type="file"
        className="sr-only"
        multiple={multiple}
        accept={accept}
        disabled={disabled}
        data-testid="attachment-input"
        onChange={(e) => {
          if (e.target.files?.length) ingest(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
