import { useEffect, useRef } from "react";
import {
  AUTO_EXAMPLE_PROMPTS,
  AUTO_MODE_KEY,
  EXAMPLE_PROMPTS,
} from "../../contracts/modes.generated";
import type { Conversation } from "../../domain/conversation";
import { AUTO_MODE_HELP } from "../../lib/modes";
import { useStickToBottom } from "../../lib/use-stick-to-bottom";
import { ChatMessages } from "../layout/ChatMain";
import { UserBubble } from "./UserBubble";
import { AssistantTurnView } from "../turn/AssistantTurnView";
import type { StampedEvent } from "../../contracts";
import type { TraceState, TurnTimeline, Verbosity } from "../../projectors";
import { EMPTY_TURN_TIMELINE } from "../../projectors";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";
import { ChevronDown, Sparkles } from "lucide-react";
import { TraceAccordion } from "../trace/TraceAccordion";

function WelcomePanel({
  title,
  subtitle,
  prompts,
  onExampleSelect,
}: {
  readonly title: string;
  readonly subtitle: string;
  readonly prompts: readonly { readonly key: string; readonly text: string }[];
  readonly onExampleSelect?: (prompt: string, exampleMode: string) => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-7 py-12 text-center">
      <div
        className={cn(
          "inline-flex size-14 items-center justify-center rounded-[var(--radius-xl)]",
          "bg-[var(--fill-hover)] text-[var(--text)] ring-1 ring-[var(--border)]",
        )}
      >
        <Sparkles size={26} strokeWidth={1.75} />
      </div>
      <div className="max-w-lg">
        <h2 className="m-0 text-[1.75rem] font-semibold tracking-tight text-[var(--text)]">
          {title}
        </h2>
        <p className="m-0 mt-2.5 text-[0.9375rem] leading-relaxed text-[var(--text-muted)]">
          {subtitle}
        </p>
      </div>
      <div className="grid w-full gap-2.5 sm:grid-cols-2">
        {prompts.map(({ key, text }) => (
          <button
            key={`${key}-${text}`}
            type="button"
            className={cn(
              "cursor-pointer rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-3.5 text-left",
              "text-[0.875rem] leading-snug text-[var(--text-muted)] transition-all",
              "hover:border-[var(--text-faint)] hover:bg-[var(--fill-hover)] hover:text-[var(--text)]",
              "shadow-[var(--shadow-card)]",
              focusRing,
            )}
            onClick={() => onExampleSelect?.(text, key)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}

function autoWelcomePrompts() {
  return AUTO_EXAMPLE_PROMPTS.map((text) => ({ key: AUTO_MODE_KEY, text }));
}

function ConversationThread({
  conversation,
  liveEvents,
  liveTimeline,
  turnTimelines,
  trace,
  verbosity,
  developerMode,
}: {
  readonly conversation: Conversation;
  readonly liveEvents: readonly StampedEvent[];
  readonly liveTimeline: TurnTimeline;
  readonly turnTimelines: Readonly<Record<string, TurnTimeline>>;
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
}) {
  const lastTurn = conversation.turns[conversation.turns.length - 1];
  const scrollKey = `${lastTurn?.runId ?? ""}:${lastTurn?.answer.length ?? 0}:${liveEvents.length}:${liveTimeline.process.length}:${liveTimeline.phase}`;
  const { bottomRef, scrollToBottom, pinForNewTurn, showScrollButton } = useStickToBottom(scrollKey);
  const prevTurnCountRef = useRef(conversation.turns.length);

  useEffect(() => {
    if (conversation.turns.length > prevTurnCountRef.current) {
      pinForNewTurn();
    }
    prevTurnCountRef.current = conversation.turns.length;
  }, [conversation.turns.length, pinForNewTurn]);

  return (
    <ChatMessages>
      <div className="relative flex flex-col gap-10">
        {conversation.turns.map((turn, index) => {
          const isLast = index === conversation.turns.length - 1;
          const events = isLast ? liveEvents : [];
          const historicalStatus =
            turn.status === "completed"
              ? ("completed" as const)
              : turn.status === "failed"
                ? ("failed" as const)
                : turn.status === "running" || turn.status === "pending"
                  ? ("running" as const)
                  : ("idle" as const);
          const cached = turnTimelines[turn.runId];
          const timeline: TurnTimeline = isLast
            ? liveTimeline
            : cached
              ? {
                  ...cached,
                  // Prefer persisted answer text if journal projection empty.
                  finalAnswer: cached.finalAnswer || turn.answer,
                  files: cached.files.length ? cached.files : (turn.files ?? []),
                }
              : {
                  ...EMPTY_TURN_TIMELINE,
                  finalAnswer: turn.answer,
                  status: historicalStatus,
                  files: turn.files ?? [],
                };
          return (
            <div key={turn.runId} className="flex flex-col gap-5">
              <UserBubble turn={turn} />
              <AssistantTurnView turn={turn} timeline={timeline} />
              {developerMode && isLast && events.length > 0 ? (
                <div className="pl-11">
                  <TraceAccordion events={events} trace={trace} verbosity={verbosity} />
                </div>
              ) : null}
            </div>
          );
        })}
        <div ref={bottomRef} />
        {showScrollButton ? (
          <button
            type="button"
            className={cn(
              "sticky bottom-2 z-10 mx-auto flex size-9 cursor-pointer items-center justify-center",
              "rounded-full border border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)]",
              "shadow-[var(--shadow-popover)] hover:bg-[var(--fill-hover)]",
              focusRing,
            )}
            onClick={() => scrollToBottom()}
            aria-label="回到底部"
          >
            <ChevronDown size={16} />
          </button>
        ) : null}
      </div>
    </ChatMessages>
  );
}

export function ThreadView({
  conversation,
  liveEvents,
  liveTimeline,
  turnTimelines,
  trace,
  verbosity,
  developerMode,
  mode,
  onExampleSelect,
}: {
  readonly conversation: Conversation | null;
  readonly liveEvents: readonly StampedEvent[];
  readonly liveTimeline: TurnTimeline;
  readonly turnTimelines: Readonly<Record<string, TurnTimeline>>;
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
  readonly mode: string;
  readonly onExampleSelect?: (prompt: string, exampleMode: string) => void;
}) {
  const isEmpty = !conversation || conversation.turns.length === 0;

  if (isEmpty) {
    if (mode === AUTO_MODE_KEY) {
      return (
        <WelcomePanel
          title="有什么可以帮忙的？"
          subtitle={AUTO_MODE_HELP}
          prompts={autoWelcomePrompts()}
          onExampleSelect={onExampleSelect}
        />
      );
    }
    const prompts =
      (EXAMPLE_PROMPTS as Record<string, readonly string[]>)[mode] ?? [];
    return (
      <WelcomePanel
        title="开始对话"
        subtitle="选择示例或直接在下方输入问题"
        prompts={prompts.map((text: string) => ({ key: mode, text }))}
        onExampleSelect={onExampleSelect}
      />
    );
  }

  return (
    <ConversationThread
      conversation={conversation}
      liveEvents={liveEvents}
      liveTimeline={liveTimeline}
      turnTimelines={turnTimelines}
      trace={trace}
      verbosity={verbosity}
      developerMode={developerMode}
    />
  );
}
