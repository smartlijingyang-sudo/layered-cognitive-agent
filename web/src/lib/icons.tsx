/**
 * LobeHub-aligned icon scale (from @lobehub/ui Icon calcSize).
 * Always use these sizes + strokeWidth=2 unless a control explicitly needs emphasis.
 */
import type { LucideIcon, LucideProps } from "lucide-react";
import { cn } from "./cn";

/** Pixel sizes matching LobeHub Icon / ActionIcon conventions. */
export const ICON_SIZE = {
  /** Dense chrome: chevrons in pills, warning badge inset */
  xs: 12,
  /** lobe-ui `small` — list rows, accordion chevrons, secondary labels */
  sm: 14,
  /** Header ActionIcon, tool neural loader, default toolbar */
  md: 16,
  /** Chat input primary actions (Plus block icon) */
  lg: 18,
  /** Large header / empty-state mark */
  xl: 20,
  /** Welcome / brand mark */
  hero: 22,
} as const;

export type IconSizeToken = keyof typeof ICON_SIZE;

/** Default stroke — LobeHub Icon always uses 2. */
export const ICON_STROKE = 2;

/** Emphasized stroke (send arrow, strong check). */
export const ICON_STROKE_BOLD = 2.5;

/** 24×24 outlined status chip (Thinking / Tool / Workflow). */
export const STATUS_BLOCK_PX = 24;

/** Icon inside status block (LobeHub: 1em of fontSize 12 ≈ 12, neural uses 16). */
export const STATUS_ICON_PX = 14;
export const STATUS_NEURAL_PX = 16;

/** Header ActionIcon: block 28 / glyph 16 (DESKTOP_HEADER_ICON_SMALL_SIZE). */
export const HEADER_ICON_BLOCK = 28;
export const HEADER_ICON_GLYPH = ICON_SIZE.md;

/** Composer action hit target: block 32 / glyph 16–18. */
export const COMPOSER_ACTION_BLOCK = 32;
export const COMPOSER_ACTION_GLYPH = ICON_SIZE.lg;

export type LobeIconProps = Omit<LucideProps, "size" | "strokeWidth" | "ref"> & {
  readonly icon: LucideIcon;
  /** Named token or raw px. Default `md` (16). */
  readonly size?: IconSizeToken | number;
  readonly strokeWidth?: number;
  readonly className?: string;
};

function resolveSize(size: IconSizeToken | number | undefined): number {
  if (size == null) return ICON_SIZE.md;
  if (typeof size === "number") return size;
  return ICON_SIZE[size];
}

/**
 * Lucide wrapper that enforces LobeHub stroke/size defaults.
 * Prefer this over raw `<Icon size={…} />` for consistent chrome.
 */
export function LobeIcon({
  icon: Svg,
  size = "md",
  strokeWidth = ICON_STROKE,
  className,
  ...rest
}: LobeIconProps) {
  const px = resolveSize(size);
  return (
    <Svg
      size={px}
      width={px}
      height={px}
      strokeWidth={strokeWidth}
      className={cn("lobe-icon shrink-0", className)}
      aria-hidden={rest["aria-hidden"] ?? true}
      {...rest}
    />
  );
}
