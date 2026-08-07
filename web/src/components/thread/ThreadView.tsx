import { EXAMPLE_PROMPTS } from "../../contracts/modes.generated";
import type { Conversation } from "../../domain/conversation";
import { AssistantBubble } from "./AssistantBubble";
import { UserBubble } from "./UserBubble";
import type { StampedEvent } from "../../contracts";
import type { TraceState, Verbosity } from "../../projectors";
import { cn } from "../../lib/cn";
import { focusRing, mutedText } from "../../lib/ui";

const WELCOME_MODES = ["board", "pipeline", "solo"] as const;

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
    <div className="flex flex-col gap-4">
      <h2 className="m-0 text-xl font-semibold">{title}</h2>
      <p className={cn("m-0", mutedText)}>{subtitle}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {prompts.map(({ key, text }) => (
          <button
            key={`${key}-${text}`}
            type="button"
            className={cn(
              "cursor-pointer rounded-[var(--radius-md)] border border-dashed border-border bg-surface p-3 text-left text-text-muted transition-colors hover:border-accent/50 hover:text-text",
              focusRing,
            )}
            onClick={() => onExampleSelect?.(text, key)}
          >
            {text}
          </button>
        ))}
      </div>
      <p className={cn("m-0 text-sm", mutedText)}>历史仅保存在本机浏览器，不会跨设备同步。</p>
    </div>
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
    const prompts = (EXAMPLE_PROMPTS[mode as keyof typeof EXAMPLE_PROMPTS] ?? []).map((text) => ({
      key: mode,
      text,
    }));
    return (
      <WelcomePanel
        title="LCA 团队协作对话"
        subtitle="从左侧新建对话，或在下方直接发送第一条消息。"
        prompts={prompts}
        onExampleSelect={onExampleSelect}
      />
    );
  }

  if (conversation.turns.length === 0) {
    const prompts = WELCOME_MODES.flatMap((key) =>
      EXAMPLE_PROMPTS[key].map((text) => ({ key, text })),
    );
    return (
      <WelcomePanel
        title={conversation.title}
        subtitle="试试示例任务："
        prompts={prompts}
        onExampleSelect={onExampleSelect}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {conversation.turns.map((turn, index) => {
        const isLast = index === conversation.turns.length - 1;
        const events = isLast ? liveEvents : [];
        return (
          <div key={turn.runId} className="flex flex-col gap-3">
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
    </div>
  );
}
