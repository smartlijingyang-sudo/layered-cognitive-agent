/**
 * LobeHub ChatInput Plus — attachments submenu.
 * @see /home/lichao/lobehub/src/features/ChatInput/ActionBar/Plus/index.tsx
 */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { ChevronRight, FileUp, LibraryBig, Plus } from "lucide-react";
import type { LocalAttachment } from "../../domain/generated-file";
import { cn } from "../../lib/cn";
import { COMPOSER_ACTION_BLOCK, LobeIcon } from "../../lib/icons";
import { composerActionCircle } from "./composer-action-bar";
import { AttachmentMenuItem } from "./AttachmentMenuItem";
import {
  COMPOSER_MENU_MIN_WIDTH,
  COMPOSER_SUBMENU_WIDTH,
  composerMenuCountChip,
  composerMenuDivider,
  composerMenuPanel,
  composerMenuRowInteractive,
  ComposerMenuIcon,
} from "./composer-menu";
import {
  computeMainMenuStyle,
  type ComposerMenuPlacement,
} from "./menu-position";
import { UploadMenuRow } from "./UploadMenuRow";

const SUBMENU_HOVER_CLOSE_MS = 180;

export function PlusActionMenu({
  disabled,
  attachments,
  onPickFiles,
  onRemoveAttachment,
  menuPlacement = "topLeft",
}: {
  readonly disabled?: boolean;
  readonly attachments: readonly LocalAttachment[];
  readonly onPickFiles: (files: FileList) => void;
  readonly onRemoveAttachment: (id: string) => void;
  readonly menuPlacement?: ComposerMenuPlacement;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const submenuCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [open, setOpen] = useState(false);
  const [submenuOpen, setSubmenuOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<
    ReturnType<typeof computeMainMenuStyle> | null
  >(null);

  const attachmentCount = attachments.length;

  const close = useCallback(() => {
    setOpen(false);
    setSubmenuOpen(false);
    setMenuStyle(null);
  }, []);

  const syncMenuPos = useCallback(() => {
    const trigger = triggerRef.current;
    const menu = menuRef.current;
    if (!trigger) return;
    const anchor = trigger.getBoundingClientRect();
    const size = menu
      ? { width: menu.offsetWidth, height: menu.offsetHeight }
      : undefined;
    setMenuStyle(computeMainMenuStyle(anchor, menuPlacement, size));
  }, [menuPlacement]);

  const openSubmenu = useCallback(() => {
    if (submenuCloseTimer.current) {
      clearTimeout(submenuCloseTimer.current);
      submenuCloseTimer.current = null;
    }
    setSubmenuOpen(true);
  }, []);

  const scheduleCloseSubmenu = useCallback(() => {
    if (submenuCloseTimer.current) clearTimeout(submenuCloseTimer.current);
    submenuCloseTimer.current = setTimeout(() => setSubmenuOpen(false), SUBMENU_HOVER_CLOSE_MS);
  }, []);

  const toggleOpen = useCallback(() => {
    setOpen((wasOpen) => {
      if (wasOpen) {
        setSubmenuOpen(false);
        setMenuStyle(null);
        return false;
      }
      if (attachments.length > 0) setSubmenuOpen(true);
      return true;
    });
  }, [attachments.length]);

  useEffect(() => {
    return () => {
      if (submenuCloseTimer.current) clearTimeout(submenuCloseTimer.current);
    };
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    syncMenuPos();
  }, [open, syncMenuPos, attachments.length, submenuOpen]);

  useEffect(() => {
    if (!open) return;
    const onLayout = () => syncMenuPos();
    window.addEventListener("resize", onLayout);
    window.addEventListener("scroll", onLayout, true);
    return () => {
      window.removeEventListener("resize", onLayout);
      window.removeEventListener("scroll", onLayout, true);
    };
  }, [open, syncMenuPos]);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };

    const timer = window.setTimeout(() => {
      document.addEventListener("pointerdown", onPointerDown);
      document.addEventListener("keydown", onKeyDown);
    }, 0);

    return () => {
      clearTimeout(timer);
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [close, open]);

  useEffect(() => {
    if (!open) return;
    const onDocDragEnter = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes("Files")) openSubmenu();
    };
    document.addEventListener("dragenter", onDocDragEnter);
    return () => document.removeEventListener("dragenter", onDocDragEnter);
  }, [open, openSubmenu]);

  const menuPortal =
    open
      ? createPortal(
          <div
            ref={menuRef}
            role="menu"
            className={cn(
              "fixed z-[1000]",
              composerMenuPanel,
              menuStyle ? "visible" : "invisible",
            )}
            style={{
              minWidth: COMPOSER_MENU_MIN_WIDTH,
              left: menuStyle?.left ?? 0,
              top: menuStyle?.top ?? 0,
              transform: menuStyle?.transform,
            }}
          >
            {/* Hover bridge: submenu absolute adjacent — LobeHub base-ui submenu. */}
            <div
              className="relative"
              onMouseEnter={openSubmenu}
              onMouseLeave={scheduleCloseSubmenu}
            >
              <div
                role="menuitem"
                aria-haspopup="menu"
                aria-expanded={submenuOpen}
                className={composerMenuRowInteractive}
                onClick={() => setSubmenuOpen((v) => !v)}
              >
                <ComposerMenuIcon>
                  <LobeIcon icon={LibraryBig} size={20} />
                </ComposerMenuIcon>
                <span className="inline-flex min-w-0 flex-1 items-center gap-2">
                  <span className="truncate">附件</span>
                  {attachmentCount > 0 ? (
                    <span className={composerMenuCountChip}>{attachmentCount}</span>
                  ) : null}
                </span>
                <LobeIcon
                  icon={ChevronRight}
                  size="md"
                  className="lobe-submenu-chevron shrink-0 text-[var(--text-faint)]"
                />
              </div>

              {submenuOpen ? (
                <div
                  role="menu"
                  className={cn(
                    "absolute top-0 z-[1001]",
                    "max-h-[min(50vh,640px)] overflow-y-auto overscroll-contain",
                    composerMenuPanel,
                    /* overlap parent by 4px — hover bridge */
                    "left-full -ml-1 pl-1",
                  )}
                  style={{ width: COMPOSER_SUBMENU_WIDTH }}
                  data-testid="attachments-submenu"
                  onMouseEnter={openSubmenu}
                  onMouseLeave={scheduleCloseSubmenu}
                >
                  <UploadMenuRow
                    disabled={disabled}
                    onFiles={onPickFiles}
                    onAfterPick={close}
                    icon={<LobeIcon icon={FileUp} size={20} />}
                    label="上传文件或图片"
                  />

                  {attachments.length > 0 ? (
                    <>
                      <div role="separator" className={composerMenuDivider} />
                      {attachments.map((att) => (
                        <AttachmentMenuItem
                          key={att.id}
                          att={att}
                          onToggle={onRemoveAttachment}
                        />
                      ))}
                    </>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <div ref={rootRef} className="relative shrink-0" data-testid="plus-action-menu">
      <button
        ref={triggerRef}
        type="button"
        className={cn(
          composerActionCircle,
          "relative cursor-pointer text-[var(--text-muted)]",
          "transition-colors hover:bg-[var(--fill-hover)] hover:text-[var(--text)]",
          disabled && "pointer-events-none opacity-50",
        )}
        style={{ width: COMPOSER_ACTION_BLOCK, height: COMPOSER_ACTION_BLOCK }}
        title="添加文件、技能和更多上下文…"
        aria-label="添加文件、技能和更多上下文"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onClick={toggleOpen}
        onMouseEnter={() => {
          if (open) openSubmenu();
        }}
      >
        <LobeIcon icon={Plus} size="lg" />
        {attachmentCount > 0 ? (
          <span className="absolute -top-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full bg-[var(--accent)] text-[9px] font-medium text-[var(--accent-fg)]">
            {attachmentCount}
          </span>
        ) : null}
      </button>

      {menuPortal}
    </div>
  );
}
