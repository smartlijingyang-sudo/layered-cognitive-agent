import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
  type UIEvent,
} from "react";
import { ChevronDown, Maximize2, Minimize2 } from "lucide-react";
import type { ThinkingBlock, ToolBlock } from "../../projectors/types";
import { formatProcessDuration } from "../../lib/format-duration";
import { LobeIcon } from "../../lib/icons";
import { cn } from "../../lib/cn";
import { focusRing, iconButton } from "../../lib/ui";
import { StatusBlock } from "./StatusBlock";
import {
  areWorkflowToolsComplete,
  getToolHeadlineLine,
  getWorkflowCompletionStatus,
  getWorkflowSummaryText,
} from "./tool-display";
import {
  WORKFLOW_EASE_CSS,
  WORKFLOW_EXPANDED_SCROLL_THRESHOLD_PX,
  WORKFLOW_HEADLINE_DEBOUNCE_MS,
  WORKFLOW_SEMI_MAX_HEIGHT_CSS,
  WORKFLOW_STREAMING_TITLE_MIN_HEIGHT_PX,
  WORKFLOW_WORKING_ELAPSED_SHOW_AFTER_MS,
} from "./workflow-constants";

export type WorkflowExpandLevel = "collapsed" | "semi" | "full";

interface WorkflowCollapseProps {
  readonly tools: readonly ToolBlock[];
  readonly thinkingDurationMs?: number;
  readonly startedAtMs?: number;
  /** Expanded body (tool cards, optional intermediate blocks). */
  readonly children: ReactNode;
  /** Force expand level defaults (streaming vs completion). */
  readonly defaultLevel?: WorkflowExpandLevel;
}

function useDebouncedHeadline(raw: string, streaming: boolean): string {
  const [out, setOut] = useState(raw);
  useEffect(() => {
    if (!streaming) {
      setOut(raw);
      return;
    }
    const id = window.setTimeout(() => setOut(raw), WORKFLOW_HEADLINE_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [raw, streaming]);
  return streaming ? out : raw;
}

/**
 * LobeHub multi-tool process shell:
 * - streaming: neural status + shiny rotating headline + elapsed
 * - done: ✓ + "N 次调用：启用了工具, …" + duration
 * - expand: collapsed | semi (scroll) | full
 */
export function WorkflowCollapse({
  tools,
  thinkingDurationMs,
  startedAtMs,
  children,
  defaultLevel,
}: WorkflowCollapseProps) {
  const allComplete = areWorkflowToolsComplete(tools);
  const streaming = !allComplete;
  const completionStatus = useMemo(() => getWorkflowCompletionStatus(tools), [tools]);
  const summaryText = useMemo(
    () => getWorkflowSummaryText(tools, thinkingDurationMs),
    [tools, thinkingDurationMs],
  );

  const totalLatencyMs = useMemo(
    () => tools.reduce((sum, t) => sum + (t.latencyMs ?? 0), 0),
    [tools],
  );
  const durationText =
    totalLatencyMs > 0 ? formatProcessDuration(totalLatencyMs) : undefined;

  const lastTool = tools.at(-1);
  const streamingHeadlineRaw = useMemo(() => {
    if (tools.length === 0) return "处理中…";
    if (lastTool && (lastTool.status === "running" || lastTool.status === "pending")) {
      return getToolHeadlineLine(lastTool);
    }
    if (lastTool) return getToolHeadlineLine(lastTool);
    return `${tools.length} 次工具调用`;
  }, [tools, lastTool]);

  const streamingHeadline = useDebouncedHeadline(streamingHeadlineRaw, streaming);

  const [expandLevel, setExpandLevel] = useState<WorkflowExpandLevel>(() => {
    if (defaultLevel) return defaultLevel;
    return streaming ? "semi" : "collapsed";
  });
  const userOpenedRef = useRef(false);
  const prevCompleteRef = useRef(allComplete);

  useEffect(() => {
    const wasComplete = prevCompleteRef.current;
    prevCompleteRef.current = allComplete;
    if (!allComplete && wasComplete) {
      userOpenedRef.current = false;
      setExpandLevel("semi");
      return;
    }
    if (allComplete && !wasComplete && !userOpenedRef.current && tools.length > 0) {
      setExpandLevel("collapsed");
    }
  }, [allComplete, tools.length]);

  const isExpanded = expandLevel !== "collapsed";
  const constrained = expandLevel === "semi";

  // Working elapsed timer
  const [elapsedSec, setElapsedSec] = useState(0);
  useEffect(() => {
    if (!streaming) {
      setElapsedSec(0);
      return;
    }
    const origin = startedAtMs ?? Date.now();
    const tick = () => setElapsedSec(Math.floor((Date.now() - origin) / 1000));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [streaming, startedAtMs]);

  const showElapsed =
    streaming && elapsedSec >= WORKFLOW_WORKING_ELAPSED_SHOW_AFTER_MS / 1000;
  const elapsedText = showElapsed
    ? formatProcessDuration(elapsedSec * 1000)
    : undefined;

  const scrollRef = useRef<HTMLDivElement>(null);
  const stickBottomRef = useRef(true);

  const handleScroll = useCallback((e: UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickBottomRef.current = dist <= WORKFLOW_EXPANDED_SCROLL_THRESHOLD_PX;
  }, []);

  useEffect(() => {
    if (!constrained || !stickBottomRef.current || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [tools.length, constrained, children]);

  const statusVariant = streaming
    ? "neural"
    : completionStatus === "error"
      ? "error"
      : completionStatus === "partial"
        ? "partial"
        : "success";

  const toggleCollapse = () => {
    if (isExpanded) {
      setExpandLevel("collapsed");
    } else {
      setExpandLevel("semi");
      userOpenedRef.current = true;
    }
  };

  const toggleSemiFull = (e: MouseEvent) => {
    e.stopPropagation();
    if (expandLevel === "semi") {
      setExpandLevel("full");
      userOpenedRef.current = true;
    } else if (expandLevel === "full") {
      setExpandLevel("semi");
    }
  };

  return (
    <div className="lobe-workflow min-w-0">
      <div className="flex items-center gap-1">
        <button
          type="button"
          className={cn(
            "lobe-accordion-trigger flex min-w-0 flex-1 cursor-pointer items-center gap-1.5",
            "border-0 bg-transparent py-1 text-left",
            focusRing,
          )}
          onClick={toggleCollapse}
          aria-expanded={isExpanded}
        >
          <StatusBlock variant={statusVariant} />
          {streaming ? (
            <div
              className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden"
              style={{ minHeight: WORKFLOW_STREAMING_TITLE_MIN_HEIGHT_PX }}
            >
              <span
                key={streamingHeadline}
                className="lobe-shiny lobe-headline-enter min-w-0 truncate text-sm"
              >
                {streamingHeadline || "处理中…"}
              </span>
              {elapsedText ? (
                <span className="shrink-0 text-xs text-[var(--text-faint)]">
                  ({elapsedText})
                </span>
              ) : null}
            </div>
          ) : (
            <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
              <span className="min-w-0 truncate text-sm text-[var(--text-muted)]">
                {summaryText}
              </span>
              {durationText ? (
                <span className="shrink-0 text-xs text-[var(--text-faint)]">{durationText}</span>
              ) : null}
            </div>
          )}
          <LobeIcon
            icon={ChevronDown}
            size="sm"
            className={cn(
              "shrink-0 text-[var(--text-faint)] transition-transform",
              isExpanded ? "rotate-180" : "",
            )}
            style={{ transitionDuration: "180ms", transitionTimingFunction: WORKFLOW_EASE_CSS }}
          />
        </button>

        {isExpanded ? (
          <button
            type="button"
            className={cn(iconButton, "size-6 shrink-0")}
            title={expandLevel === "semi" ? "全部展开" : "收起高度"}
            onClick={toggleSemiFull}
          >
            {expandLevel === "semi" ? (
              <LobeIcon icon={Maximize2} size="xs" />
            ) : (
              <LobeIcon icon={Minimize2} size="xs" />
            )}
          </button>
        ) : null}
      </div>

      <div
        className={cn(
          "grid transition-[grid-template-rows,opacity]",
          isExpanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
        )}
        style={{
          transitionDuration: "220ms",
          transitionTimingFunction: WORKFLOW_EASE_CSS,
        }}
      >
        <div className="min-h-0 overflow-hidden">
          <div
            ref={scrollRef}
            onScroll={constrained ? handleScroll : undefined}
            className={cn(
              "lobe-workflow-body mt-1 py-1 pl-0.5",
              constrained && "lobe-workflow-scroll overflow-y-auto pr-2",
            )}
            style={constrained ? { maxHeight: WORKFLOW_SEMI_MAX_HEIGHT_CSS } : undefined}
          >
            <div className="grid gap-2">{children}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Sum thinking duration from process thinking blocks. */
export function sumThinkingDuration(blocks: readonly ThinkingBlock[]): number {
  return blocks.reduce((sum, b) => sum + (b.durationMs ?? 0), 0);
}
