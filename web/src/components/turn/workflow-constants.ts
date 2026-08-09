/**
 * LobeHub-aligned workflow / process UI constants.
 * Keep magic numbers out of components (AGENTS.md).
 */

/** Elapsed timer on working header only after this many ms. */
export const WORKFLOW_WORKING_ELAPSED_SHOW_AFTER_MS = 2100;

/** Debounce streaming headline changes (ms). */
export const WORKFLOW_HEADLINE_DEBOUNCE_MS = 320;

/** Min height for streaming title row (px). */
export const WORKFLOW_STREAMING_TITLE_MIN_HEIGHT_PX = 22;

/** Auto-scroll stickiness margin in semi-expanded workflow list (px). */
export const WORKFLOW_EXPANDED_SCROLL_THRESHOLD_PX = 120;

/** Semi-expand max height: min(40vh, 320px) — applied via CSS class. */
export const WORKFLOW_SEMI_MAX_HEIGHT_CSS = "min(40vh, 320px)";

/** Thinking / workflow body max height. */
export const THINKING_BODY_MAX_HEIGHT_CSS = "min(40vh, 320px)";

/** Status / control block size (LobeHub 24×24 outlined). */
export const STATUS_BLOCK_SIZE_PX = 24;

/** Tool first-arg preview cap. */
export const TOOL_FIRST_DETAIL_MAX_CHARS = 80;

/** Tool headline detail soft cap. */
export const TOOL_HEADLINE_DETAIL_MAX_CHARS = 120;

export const TOOL_HEADLINE_TRUNCATION_SUFFIX = "…";

/** Workflow summary: show top-N tool kinds when many. */
export const WORKFLOW_SUMMARY_TOP_N = 3;

/** Multi-tool fold threshold — single tool stays inline. */
export const WORKFLOW_MULTI_TOOL_THRESHOLD = 2;

/** Motion easing matching LobeHub Accordion / headline. */
export const WORKFLOW_EASE_CSS = "cubic-bezier(0.4, 0, 0.2, 1)";

export const WORKFLOW_EXPAND_DURATION_MS = 180;
export const WORKFLOW_HEADLINE_MOTION_MS = 200;
