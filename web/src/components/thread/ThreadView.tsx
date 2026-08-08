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
import { AssistantBubble } from "./AssistantBubble";
import { UserBubble } from "./UserBubble";
import type { StampedEvent } from "../../contracts";
import type { TraceState, Verbosity } from "../../projectors";
import { cn } from "../../lib/cn";
import { focusRing } from "../../lib/ui";
import { ChevronDown, Sparkles } from "lucide-react";

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
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-6 py-8 text-center">
      <div className="inline-flex size-14 items-center justify-center rounded-[var(--radius-xl)] bg-accent/12 text-accent ring-1 ring-accent/20">
        <Sparkles size={26} strokeWidth={1.75} />
      </div>
      <div className="max-w-lg">
        <h2 className="m-0 text-2xl font-semibold tracking-tight">{title}</h2>
        <p className="m-0 mt-2 text-[0.9375rem] leading-relaxed text-[var(--text-muted)]">{subtitle}</p>
      </div>
      <div className="grid w-full gap-2.5 sm:grid-cols-2">
        {prompts.map(({ key, text }) => (
          <button
            key={`${key}-${text}`}
            type="button"
            className={cn(
              "cursor-pointer rounded-[var(--radius-lg)] border border-border/70 bg-surface p-3.5 text-left",
              "text-[0.875rem] leading-snug text-[var(--text-muted)] transition-all",
              "hover:border-accent/40 hover:bg-surface-elevated hover:text-text hover:shadow-sm",
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
  trace,
  verbosity,
  developerMode,
}: {
  readonly conversation: Conversation;
  readonly liveEvents: readonly StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
}) {
  const lastTurn = conversation.turns[conversation.turns.length - 1];
  const scrollKey = `${lastTurn?.runId ?? ""}:${lastTurn?.answer.length ?? 0}:${liveEvents.length}:${trace.phase}`;
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
          return (
            <div key={turn.runId} className="flex flex-col gap-5">
              <UserBubble turn={turn} />
              <AssistantBubble
                turn={turn}
                events={events}
                trace={isLast ? trace : trace}
                verbosity={verbosity}
                developerMode={developerMode}
              />
            </div>
          );
        })}
        <div ref={bottomRef} aria-hidden className="h-px shrink-0" />
      </div>
      {showScrollButton ? (
        <button
          type="button"
          className={cn(
            "fixed bottom-[7.5rem] left-1/2 z-30 inline-flex -translate-x-1/2 items-center gap-1.5",
            "rounded-full border border-border/80 bg-surface px-3.5 py-2 text-sm shadow-lg",
            "text-text backdrop-blur-md transition-opacity",
            focusRing,
          )}
          onClick={scrollToBottom}
        >
          <ChevronDown size={16} />
          回到底部
        </button>
      ) : null}
    </ChatMessages>
  );
}

export function ThreadView({
  conversation,
  liveEvents,
  trace,
  verbosity,
  developerMode,
  mode,
  onExampleSelect,
}: {
  readonly conversation: Conversation | null;
  readonly liveEvents: readonly StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
  readonly mode: string;
  readonly onExampleSelect?: (prompt: string, exampleMode: string) => void;
}) {
  if (!conversation) {
    const prompts =
      mode === AUTO_MODE_KEY
        ? autoWelcomePrompts()
        : (EXAMPLE_PROMPTS[mode as keyof typeof EXAMPLE_PROMPTS] ?? []).map((text) => ({
            key: mode,
            text,
          }));
    return (
      <WelcomePanel
        title="开始对话"
        subtitle={
          mode === AUTO_MODE_KEY
            ? `智能组队 · ${AUTO_MODE_HELP} 选示例或直接在下方输入。`
            : "从左侧新建对话，或在下方输入第一条消息。"
        }
        prompts={prompts}
        onExampleSelect={onExampleSelect}
      />
    );
  }

  if (conversation.turns.length === 0) {
    return (
      <WelcomePanel
        title={conversation.title}
        subtitle="试试下方示例，或直接输入你的问题"
        prompts={autoWelcomePrompts()}
        onExampleSelect={onExampleSelect}
      />
    );
  }

  return (
    <ConversationThread
      conversation={conversation}
      liveEvents={liveEvents}
      trace={trace}
      verbosity={verbosity}
      developerMode={developerMode}
    />
  );
}
