import { MODE_DEFAULT_OBJECTIVE } from "../../contracts/catalog.generated";
import type { Conversation } from "../../domain/conversation";
import { AssistantBubble } from "./AssistantBubble";
import { UserBubble } from "./UserBubble";
import type { StampedEvent } from "../../contracts";
import type { TraceState, Verbosity } from "../../projectors";

export function ThreadView({
  conversation,
  liveEvents,
  trace,
  verbosity,
  developerMode,
  mode,
}: {
  readonly conversation: Conversation | null;
  readonly liveEvents: readonly StampedEvent[];
  readonly trace: TraceState;
  readonly verbosity: Verbosity;
  readonly developerMode: boolean;
  readonly mode: string;
}) {
  if (!conversation) {
    return (
      <div className="welcome">
        <h2>LCA 团队协作对话</h2>
        <p className="muted">从左侧新建对话，或在下方直接发送第一条消息。</p>
        <div className="prompt-grid">
          <button type="button" className="prompt-chip" data-mode={mode}>
            {MODE_DEFAULT_OBJECTIVE[mode as keyof typeof MODE_DEFAULT_OBJECTIVE]?.slice(0, 80) ??
              "开始一个新任务"}
          </button>
        </div>
        <p className="storage-note">历史仅保存在本机浏览器，不会跨设备同步。</p>
      </div>
    );
  }

  if (conversation.turns.length === 0) {
    return (
      <div className="welcome">
        <h2>{conversation.title}</h2>
        <p className="muted">试试示例任务：</p>
        <div className="prompt-grid">
          {(["board", "pipeline", "solo"] as const).map((key) => (
            <button key={key} type="button" className="prompt-chip" data-mode={key}>
              {MODE_DEFAULT_OBJECTIVE[key].slice(0, 96)}…
            </button>
          ))}
        </div>
        <p className="storage-note">历史仅保存在本机浏览器，不会跨设备同步。</p>
      </div>
    );
  }

  return (
    <div className="thread">
      {conversation.turns.map((turn, index) => {
        const isLast = index === conversation.turns.length - 1;
        const events = isLast ? liveEvents : [];
        return (
          <div key={turn.runId} className="turn-block">
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
