/**
 * LobeHub ChatInput Plus — uploadItems when knowledge base is disabled.
 * @see /home/lichao/lobehub/src/features/ChatInput/ActionBar/Plus/index.tsx
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { FileUp, Plus } from "lucide-react";
import { cn } from "../../lib/cn";
import { COMPOSER_ACTION_BLOCK, ICON_SIZE, LobeIcon } from "../../lib/icons";
import { focusRing } from "../../lib/ui";

const MENU_ICON_PX = ICON_SIZE.xl;

export function PlusActionMenu({
  disabled,
  attachmentCount,
  onPickFiles,
}: {
  readonly disabled?: boolean;
  readonly attachmentCount: number;
  readonly onPickFiles: (files: FileList) => void;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [close, open]);

  return (
    <div ref={rootRef} className="relative shrink-0" data-testid="plus-action-menu">
      <button
        type="button"
        className={cn(
          "relative inline-flex cursor-pointer items-center justify-center rounded-full",
          "text-[var(--text-muted)] transition-colors hover:bg-[var(--fill-hover)] hover:text-[var(--text)]",
          disabled && "pointer-events-none opacity-50",
          focusRing,
        )}
        style={{ width: COMPOSER_ACTION_BLOCK, height: COMPOSER_ACTION_BLOCK }}
        title="添加文件、技能和更多上下文…"
        aria-label="添加文件、技能和更多上下文"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
      >
        <LobeIcon icon={Plus} size="lg" />
        {attachmentCount > 0 ? (
          <span className="absolute -top-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full bg-[var(--accent)] text-[9px] font-medium text-[var(--accent-fg)]">
            {attachmentCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          role="menu"
          className={cn(
            "absolute bottom-full left-0 z-50 mb-2 min-w-[220px] overflow-hidden",
            "rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-elevated)]",
            "py-1 shadow-[var(--shadow-popover)] animate-fade-in",
          )}
        >
          <button
            type="button"
            role="menuitem"
            className={cn(
              "flex w-full cursor-pointer items-center gap-2.5 px-3 py-2 text-left text-[13px]",
              "text-[var(--text)] transition-colors hover:bg-[var(--fill-hover)]",
              focusRing,
            )}
            onClick={() => {
              close();
              inputRef.current?.click();
            }}
          >
            <span
              className="inline-flex shrink-0 items-center justify-center text-[var(--text-muted)]"
              style={{ width: MENU_ICON_PX, height: MENU_ICON_PX }}
            >
              <LobeIcon icon={FileUp} size={MENU_ICON_PX} />
            </span>
            <span className="min-w-0 flex-1 truncate">上传文件或图片</span>
          </button>
        </div>
      ) : null}

      <input
        ref={inputRef}
        id={inputId}
        type="file"
        className="sr-only"
        multiple
        disabled={disabled}
        data-testid="attachment-input"
        onChange={(e) => {
          if (e.target.files?.length) onPickFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
