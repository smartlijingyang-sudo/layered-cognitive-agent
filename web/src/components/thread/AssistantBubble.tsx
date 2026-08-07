import type { Turn } from "../../domain/conversation";
import type { TraceState, Verbosity } from "../../projectors";
import { phaseStatusLabel } from "../shared/RunProgressBar";
import { MarkdownContent } from "../shared/MarkdownContent";
import { ProgressiveReveal } from "../shared/ProgressiveReveal";
import { RunProgressBar } from "../shared/RunProgressBar";
import { TypingIndicator } from "../shared/TypingIndicator";
import { TraceAccordion } from "../trace/TraceAccordion";
import { TeamCompositionBanner } from "./TeamCompositionBanner";
import { cn } from "../../lib/cn";
import { elevatedSurface, mutedText } from "../../lib/ui";

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
  const deltas = turn.answerDeltas ?? [];
  const hasAnswer = Boolean(turn.answer.trim());
  const showTyping = streaming && !hasAnswer && trace.phase !== "failed";
  const body =
    turn.status === "running" && !developerMode && hasAnswer ? (
      <ProgressiveReveal text={turn.answer} deltas={deltas} active={streaming} />
    ) : (
      turn.answer
    );

  return (
    <article className={cn(elevatedSurface, "border-l-[3px] border-l-run px-4 py-3.5")}>
      <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className={cn("text-xs", mutedText)}>助手 · {turnStatusLabel(turn, trace)}</span>
        {streaming ? <RunProgressBar phase={trace.phase} compact /> : null}
      </header>

      {trace.casting && turn.mode === "auto" ? (
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
              : "团队成员正在协作生成回答…"
          }
        />
      ) : null}

      {!showTyping && (developerMode || turn.status === "completed") && hasAnswer ? (
        <MarkdownContent text={turn.answer} />
      ) : null}

      {!showTyping && !hasAnswer && turn.status === "failed" ? (
        <p className={cn("m-0 text-sm", mutedText)}>未能生成回答，请查看下方轨迹或重试。</p>
      ) : null}

      {!showTyping && hasAnswer && turn.status === "running" && !developerMode ? (
        <div className="markdown-body">
          <p className="m-0">{body}</p>
        </div>
      ) : null}

      <TraceAccordion events={events} trace={trace} verbosity={verbosity} />
    </article>
  );
}
