import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";

/** LobeHub ActionDropdown menu chrome. */
export const COMPOSER_MENU_MIN_WIDTH = 220;
export const COMPOSER_SUBMENU_WIDTH = 320;
export const COMPOSER_MENU_SIDE_OFFSET = 8;
export const COMPOSER_MENU_ICON_PX = 20;

export const composerMenuPanel = cn(
  "rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-elevated)]",
  "py-1 shadow-[var(--shadow-popover)] animate-fade-in",
);

/** Shared row — icon column (20px) + label, px-3 / min-h-9 / items-center. */
export const composerMenuRow = cn(
  "flex min-h-9 w-full items-center gap-2 px-3 text-left text-sm leading-none",
  "text-[var(--text)] transition-colors hover:bg-[var(--fill-hover)]",
);

export const composerMenuIconCell = cn(
  "inline-flex shrink-0 items-center justify-center text-[var(--text-muted)]",
);

export const composerMenuCountChip = cn(
  "inline-flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-full",
  "bg-[var(--fill-secondary)] px-1.5 text-[11px] leading-[18px] text-[var(--text-muted)]",
);

export const composerMenuDivider = "mx-3 my-1 h-px bg-[var(--border-subtle)]";

export const composerMenuRowInteractive = cn(composerMenuRow, "cursor-pointer", focusRing);

export function ComposerMenuIcon({
  children,
}: {
  readonly children: ReactNode;
}) {
  return (
    <span
      className={composerMenuIconCell}
      style={{ width: COMPOSER_MENU_ICON_PX, height: COMPOSER_MENU_ICON_PX }}
    >
      {children}
    </span>
  );
}
