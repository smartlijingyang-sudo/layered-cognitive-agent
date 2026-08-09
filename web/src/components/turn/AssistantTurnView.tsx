import type { Turn } from "../../domain/conversation";
import type { TurnTimeline } from "../../projectors/types";
import { formatProcessDuration } from "../../lib/format-duration";
import { MarkdownContent } from "../shared/MarkdownContent";
import { GeneratedFileList } from "../shared/GeneratedFileCard";
import { TypingIndicator } from "../shared/TypingIndicator";
import { TeamCompositionBanner } from "../thread/TeamCompositionBanner";
import { ProcessFold } from "./ProcessFold";
import { ProcessBlocks } from "./block-registry";
import { Bot } from "lucide-react";
import { cn } from "../../lib/cn";

function phaseLabel(timeline: TurnTimeline, turn: Turn): string {
  if (turn.status === "failed" || timeline.status === "failed") return "失败";
  if (turn.status === "canceled") return "已取消";
  if (turn.status === "completed" || timeline.status === "completed") return "已完成";
  if (timeline.phase === "casting") return "智能选角";
  if (timeline.phase === "synthesizing") return "综合收口";
  if (timeline.process.some((b) => b.kind === "sandbox" && b.status === "running")) {
    return "沙箱执行";
  }
  if (timeline.process.some((b) => b.kind === "tool" && b.status === "running")) {
    return "工具调用";
  }
  if (timeline.process.some((b) => b.kind === "thinking" && b.status === "running")) {
    return "深度思考";
  }
  return "生成中";
}

/**
 * LobeHub-aligned assistant turn:
 * process blocks (optional ProcessFold when done) + final answer always outside.
 */
export function AssistantTurnView({
  turn,
  timeline,
}: {
  readonly turn: Turn;
  readonly timeline: TurnTimeline;
}) {
  const streaming = turn.status === "running" || turn.status === "pending";
  const answer = timeline.finalAnswer || turn.answer;
  const hasAnswer = Boolean(answer.trim());
  const process = timeline.process;
  const hasProcess = process.length > 0;
  const showTyping = streaming && !hasAnswer && !hasProcess && timeline.phase !== "failed";
  const castingDone = process.find(
    (b): b is Extract<(typeof process)[number], { kind: "casting" }> =>
      b.kind === "casting" && b.status === "done",
  );

  const processBody = hasProcess ? <ProcessBlocks blocks={process} /> : null;

  return (
    <div className="flex gap-3">
      <div
        className={cn(
          "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
          "bg-[var(--fill-hover)] text-[var(--text-muted)] ring-1 ring-[var(--border)]",
        )}
        aria-hidden
      >
        <Bot size={16} strokeWidth={2} />
      </div>

      <div className="min-w-0 flex-1">
        {streaming || turn.status === "failed" || turn.status === "canceled" ? (
          <div className="mb-2 text-xs font-medium text-[var(--text-faint)]">
            助手 · {phaseLabel(timeline, turn)}
          </div>
        ) : null}

        {castingDone && turn.mode === "auto" && streaming ? (
          <div className="mb-3">
            <TeamCompositionBanner
              casting={{
                governanceKind: castingDone.governanceKind ?? "",
                leadRole: castingDone.leadRole ?? "",
                selectedRoles: castingDone.selectedRoles ?? [],
                rationale: castingDone.rationale ?? "",
              }}
            />
          </div>
        ) : null}

        {showTyping ? (
          <TypingIndicator
            label={
              timeline.phase === "casting"
                ? "正在从角色库挑选合适团队…"
                : "团队成员正在协作生成回答…"
            }
          />
        ) : null}

        {hasProcess ? (
          timeline.foldProcess ? (
            <div className="mb-3">
              <ProcessFold
                stepCount={Math.max(1, timeline.stepCount)}
                durationText={formatProcessDuration(timeline.durationMs ?? 0)}
              >
                {processBody}
              </ProcessFold>
            </div>
          ) : (
            <div className="mb-3">{processBody}</div>
          )
        ) : null}

        {hasAnswer ? (
          <div className="min-w-0">
            <MarkdownContent
              text={answer}
              streaming={streaming && timeline.finalAnswerStreaming}
            />
          </div>
        ) : null}

        {(timeline.files.length > 0 || (turn.files && turn.files.length > 0)) && (
          <div className="mt-3">
            <GeneratedFileList
              files={timeline.files.length ? timeline.files : (turn.files ?? [])}
            />
          </div>
        )}

        {!showTyping && !hasAnswer && !hasProcess && turn.status === "failed" ? (
          <p className="m-0 text-sm text-[var(--text-muted)]">
            未能生成回答，请重试或开启开发者模式查看轨迹。
          </p>
        ) : null}

        {timeline.errorMessage && turn.status === "failed" ? (
          <p className="m-0 mt-2 text-sm text-[var(--color-danger)]">{timeline.errorMessage}</p>
        ) : null}
      </div>
    </div>
  );
}
