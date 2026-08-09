import { useEffect, useRef } from "react";
import type { Conversation } from "../../domain/conversation";
import { useStickToBottom } from "../../lib/use-stick-to-bottom";
import { ChatMessages } from "../layout/ChatMain";
import { UserBubble } from "./UserBubble";
import { AssistantTurnView } from "../turn/AssistantTurnView";
import type { StampedEvent } from "../../contracts";
import type { TraceState, TurnTimeline, Verbosity } from "../../projectors";
import { EMPTY_TURN_TIMELINE } from "../../projectors";
import { cn } from "../../lib/cn";
import { LobeIcon } from "../../lib/icons";
import { focusRing } from "../../lib/ui";
import { ChevronDown } from "lucide-react";
import { TraceAccordion } from "../trace/TraceAccordion";
import { HomeWelcome } from "../home/HomeWelcome";
import { TopicWelcome } from "../home/TopicWelcome";

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
            <div key={turn.runId} className="lobe-turn-pair flex flex-col gap-5">
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
              "sticky bottom-3 z-10 mx-auto flex size-9 cursor-pointer items-center justify-center",
              "rounded-full border border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)]",
              "shadow-[var(--shadow-popover)] transition-all hover:bg-[var(--fill-hover)] hover:text-[var(--text)]",
              "animate-fade-in",
              focusRing,
            )}
            onClick={() => scrollToBottom()}
            aria-label="回到底部"
          >
            <LobeIcon icon={ChevronDown} size="md" />
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
  homeActive,
  onOpenModePicker,
}: {
  readonly conversation: Conversation | null;
  readonly liveEvents: readonly StampedEvent[];
  readonly liveTimeline: TurnTimeline;
  readonly turnTimelines: Readonly<Record<string, TurnTimeline>>;
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
  readonly mode?: string;
  readonly homeActive?: boolean;
  readonly onOpenModePicker?: () => void;
  readonly onExampleSelect?: (prompt: string, exampleMode: string) => void;
}) {
  if (homeActive) {
    return <HomeWelcome agentTitle="LCA" onAgentClick={onOpenModePicker} />;
  }

  if (!conversation || conversation.turns.length === 0) {
    return <TopicWelcome agentTitle="LCA" />;
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
