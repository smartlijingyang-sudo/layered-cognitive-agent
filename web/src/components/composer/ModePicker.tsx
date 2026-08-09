import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { LucideIcon } from "lucide-react";
import { ChevronDown, MessageCircle, Users } from "lucide-react";
import { ALL_MODES, SOLO_MODE_KEY } from "../../contracts/modes.generated";
import { modeHelp, modeLabel } from "../../lib/modes";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import {
  composerModeControlBar,
  composerModePill,
  elevatedSurface,
  focusRing,
  mutedText,
} from "../../lib/ui";
import {
  computeMainMenuStyle,
  type ComposerMenuPlacement,
} from "./menu-position";

const MODE_ICONS: Record<string, LucideIcon> = {
  solo: MessageCircle,
  team: Users,
};

const MODE_PICKER_MIN_WIDTH = 280;
const MODE_PICKER_MAX_WIDTH = 320;

export function ModePicker({
  value,
  onChange,
  disabled,
  variant = "mode",
  triggerId = "lca-mode-picker-trigger",
  menuPlacement = "bottomLeft",
}: {
  readonly value: string;
  readonly onChange: (mode: string) => void;
  readonly disabled?: boolean;
  /** `mode` — action bar pill; `chat` — control bar row below composer. */
  readonly variant?: "mode" | "chat";
  readonly triggerId?: string;
  readonly menuPlacement?: ComposerMenuPlacement;
}) {
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<
    ReturnType<typeof computeMainMenuStyle> | null
  >(null);

  const CurrentIcon = MODE_ICONS[value] ?? MessageCircle;

  const syncMenuPos = useCallback(() => {
    const trigger = triggerRef.current;
    const panel = panelRef.current;
    if (!trigger) return;
    const anchor = trigger.getBoundingClientRect();
    const size = panel
      ? { width: panel.offsetWidth, height: panel.offsetHeight }
      : { width: MODE_PICKER_MIN_WIDTH, height: 160 };
    setMenuStyle(computeMainMenuStyle(anchor, menuPlacement, size));
  }, [menuPlacement]);

  const close = useCallback(() => {
    setOpen(false);
    setMenuStyle(null);
  }, []);

  const selectMode = useCallback(
    (mode: string) => {
      onChange(mode);
      close();
    },
    [close, onChange],
  );

  useLayoutEffect(() => {
    if (!open) return;
    syncMenuPos();
  }, [open, syncMenuPos, value]);

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
      if (panelRef.current?.contains(target)) return;
      close();
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

  const triggerClass = variant === "chat" ? composerModeControlBar : composerModePill;

  const popover =
    open
      ? createPortal(
          <div
            ref={panelRef}
            id={listboxId}
            role="listbox"
            aria-label="协作模式"
            className={cn(
              "fixed z-[1000] overflow-hidden p-1",
              elevatedSurface,
              "shadow-[var(--shadow-popover)] animate-fade-in",
              menuStyle ? "visible" : "invisible",
            )}
            style={{
              width: `min(${MODE_PICKER_MAX_WIDTH}px, calc(100vw - 2rem))`,
              minWidth: MODE_PICKER_MIN_WIDTH,
              left: menuStyle?.left ?? 0,
              top: menuStyle?.top ?? 0,
              transform: menuStyle?.transform,
            }}
          >
            {ALL_MODES.map((mode) => (
              <ModeOptionRow
                key={mode}
                mode={mode}
                selected={mode === value}
                onSelect={() => selectMode(mode)}
              />
            ))}
          </div>,
          document.body,
        )
      : null;

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        id={triggerId}
        className={triggerClass}
        disabled={disabled}
        title={modeHelp(value)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <LobeIcon icon={CurrentIcon} size="sm" className="shrink-0" />
        <span className="truncate font-medium">{modeLabel(value)}</span>
        <LobeIcon icon={ChevronDown} size="xs" className="shrink-0 opacity-60" />
      </button>
      {popover}
    </div>
  );
}

function ModeOptionRow({
  mode,
  selected,
  onSelect,
}: {
  readonly mode: string;
  readonly selected: boolean;
  readonly onSelect: () => void;
}) {
  const Icon = MODE_ICONS[mode] ?? MessageCircle;
  const help = modeHelp(mode);
  const badge =
    mode === SOLO_MODE_KEY ? (
      <span className="rounded-full border border-[var(--border)] bg-[var(--fill-secondary)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
        默认
      </span>
    ) : null;

  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      className={cn(
        "flex w-full cursor-pointer items-center gap-3 rounded-[var(--radius-md)] px-2 py-2.5 text-left transition-colors duration-150",
        selected ? "bg-[var(--fill-secondary)]" : "hover:bg-[var(--fill-hover)]",
        focusRing,
      )}
      onClick={onSelect}
    >
      <span
        className={cn(
          "inline-flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-md)]",
          "border border-[var(--border-subtle)] bg-[var(--surface-elevated)] text-[var(--text-muted)]",
        )}
      >
        <LobeIcon icon={Icon} size="md" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium leading-snug text-[var(--text)]">
            {modeLabel(mode)}
          </span>
          {badge}
        </span>
        {help ? (
          <span className={cn("mt-0.5 block text-xs leading-snug", mutedText)}>{help}</span>
        ) : null}
      </span>
    </button>
  );
}
