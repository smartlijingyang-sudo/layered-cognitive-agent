import { cn } from "./cn";

/** Shared Tailwind fragments — consume design-tokens.css semantic variables. */

export const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/30 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]";

export const inputField = cn(
  "w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-[var(--text)]",
  "placeholder:text-[var(--text-faint)] disabled:cursor-not-allowed disabled:opacity-60",
  focusRing,
);

export const btnPrimary = cn(
  "inline-flex cursor-pointer items-center gap-1.5 rounded-[var(--radius-md)] border-0 px-3.5 py-2 font-semibold",
  "bg-[var(--accent)] text-[var(--accent-fg)] disabled:cursor-not-allowed disabled:opacity-50",
  focusRing,
);

export const btnSecondary = cn(
  "inline-flex cursor-pointer items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--border)]",
  "bg-transparent px-3.5 py-2 text-[var(--text)] disabled:cursor-not-allowed disabled:opacity-50",
  "hover:bg-[var(--fill-hover)]",
  focusRing,
);

export const iconButton = cn(
  "inline-flex size-8 cursor-pointer items-center justify-center rounded-[var(--radius-md)] border border-transparent",
  "bg-transparent p-1.5 text-[var(--text-muted)] hover:bg-[var(--fill-hover)] hover:text-[var(--text)]",
  "disabled:cursor-not-allowed disabled:opacity-50 transition-colors duration-150",
  focusRing,
);

export const mutedText = "text-[var(--text-muted)]";

export const faintText = "text-[var(--text-faint)]";

export const panelSurface =
  "rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)]";

export const elevatedSurface =
  "rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-elevated)]";

/** LobeHub-style sidebar list item. */
export const sidebarItem = cn(
  "w-full cursor-pointer rounded-[var(--radius-md)] border border-transparent px-3 py-2 text-left",
  "text-[var(--text)] transition-colors duration-150 hover:bg-[var(--fill-hover)]",
  focusRing,
);

export const sidebarItemActive = cn(
  sidebarItem,
  "bg-[var(--fill-hover)] text-[var(--text)]",
);

/** Pill control in composer action bar — LobeHub AgentMode: h-28px. */
export const composerPill = cn(
  "inline-flex h-7 max-w-[12rem] cursor-pointer items-center gap-1.5 rounded-full",
  "border border-[var(--border)] bg-[var(--fill-secondary)] px-2 text-xs leading-none",
  "text-[var(--text-muted)] transition-colors duration-150",
  "hover:bg-[var(--fill-hover)] hover:text-[var(--text)]",
  "disabled:cursor-not-allowed disabled:opacity-50",
  focusRing,
);

/** LobeHub ActionBar AgentMode trigger — icon + label + chevron, no border. */
export const composerModePill = cn(
  "inline-flex h-7 max-w-[12rem] cursor-pointer items-center gap-1.5 rounded-full px-2",
  "bg-[color-mix(in_srgb,var(--fill-secondary)_72%,transparent)] text-xs leading-none",
  "text-[var(--text-muted)] transition-colors duration-150",
  "hover:bg-[var(--fill-secondary)] hover:text-[var(--text)]",
  "disabled:cursor-not-allowed disabled:opacity-50",
  focusRing,
);

/** LobeHub ControlBar ModeSelector — flat row below composer. */
export const composerModeControlBar = cn(
  "inline-flex h-7 max-w-[12rem] cursor-pointer items-center gap-1.5 rounded-[6px] px-2",
  "text-xs leading-none text-[var(--text-muted)] transition-colors duration-150",
  "hover:bg-[var(--fill-secondary)] hover:text-[var(--text)]",
  "disabled:cursor-not-allowed disabled:opacity-50",
  focusRing,
);

/** Soft status badge (LLM online, etc.). */
export const softBadge = cn(
  "inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)]",
  "bg-[var(--fill-secondary)] px-2 py-0.5 text-[11px] font-medium",
);
