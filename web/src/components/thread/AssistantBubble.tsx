import type { Turn } from "../../domain/conversation";
import type { TraceState, Verbosity } from "../../projectors";
import { Bot } from "lucide-react";
import { phaseStatusLabel } from "../shared/RunProgressBar";
import { MarkdownContent } from "../shared/MarkdownContent";
import { GeneratedFileList } from "../shared/GeneratedFileCard";
import { RunProgressBar } from "../shared/RunProgressBar";
import { TypingIndicator } from "../shared/TypingIndicator";
import { TraceAccordion } from "../trace/TraceAccordion";
import { TeamCompositionBanner } from "./TeamCompositionBanner";
import { cn } from "../../lib/cn";

function turnStatusLabel(turn: Turn, trace: TraceState): string {
  if (turn.status === "failed") return "失败";
  if (turn.status === "completed") return "已完成";
  if (turn.status === "canceled") return "已取消";
  return phaseStatusLabel(trace.phase);
}

export function AssistantBubble({
  turn,
  events,
  trace,
  verbosity,
  developerMode,
}: {
  readonly turn: Turn;
  readonly events: readonly import("../../contracts").StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
}) {
  const streaming = turn.status === "running" || turn.status === "pending";
  const hasAnswer = Boolean(turn.answer.trim());
  const showTyping = streaming && !hasAnswer && trace.phase !== "failed";
  const showStatus = streaming || turn.status === "failed" || turn.status === "canceled";

  return (
    <div className="flex gap-3">
      <div
        className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-accent/12 text-accent ring-1 ring-accent/20"
        aria-hidden
      >
        <Bot size={16} strokeWidth={2} />
      </div>

      <div className="min-w-0 flex-1">
        {showStatus ? (
          <div className="mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <span className="text-xs font-medium text-[var(--text-faint)]">
              助手 · {turnStatusLabel(turn, trace)}
            </span>
            {streaming ? <RunProgressBar phase={trace.phase} compact /> : null}
          </div>
        ) : null}

        {trace.casting && turn.mode === "auto" && streaming ? (
          <div className="mb-3">
            <TeamCompositionBanner casting={trace.casting} />
          </div>
        ) : null}

        {trace.castingError ? (
          <p className="m-0 mb-2 text-sm text-danger">{trace.castingError}</p>
        ) : null}

        {showTyping ? (
          <TypingIndicator
            label={
              trace.phase === "casting"
                ? "正在从角色库挑选合适团队…"
                : trace.sandboxStreams.some((s) => !s.sealed)
                  ? "沙箱正在执行代码…"
                  : "团队成员正在协作生成回答…"
            }
          />
        ) : null}

        {trace.sandboxStreams.some((s) => !s.sealed) ? (
          <div className="mb-2 max-h-28 overflow-auto rounded border border-border bg-black/15 p-2 font-mono text-xs text-[var(--text-muted)] whitespace-pre-wrap">
            {trace.sandboxStreams
              .filter((s) => !s.sealed)
              .map((s) => s.text)
              .join("")
              .slice(-800) || "…"}
          </div>
        ) : null}

        {!showTyping && hasAnswer ? (
          <MarkdownContent text={turn.answer} streaming={streaming && !developerMode} />
        ) : null}

        {turn.files && turn.files.length > 0 ? (
          <GeneratedFileList files={turn.files} />
        ) : null}

        {!showTyping && !hasAnswer && turn.status === "failed" ? (
          <p className={cn("m-0 text-sm text-[var(--text-muted)]")}>
            未能生成回答，请查看下方轨迹或重试。
          </p>
        ) : null}

        <TraceAccordion events={events} trace={trace} verbosity={verbosity} />
      </div>
    </div>
  );
}
