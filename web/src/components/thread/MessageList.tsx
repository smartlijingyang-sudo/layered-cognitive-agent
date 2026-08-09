import type { Turn } from "../../projectors/message-types";
import { MessageRenderer } from "./MessageRenderer";
import { ProcessFold } from "../turn/ProcessFold";
import { formatProcessDuration } from "../../lib/format-duration";

/**
 * LobeHub-style message list:
 * - Process messages (thinking, tool_call, casting, delegation, sandbox)
 *   are shown inline while running, folded into ProcessFold when done.
 * - Answer messages always render outside ProcessFold.
 * - Insight messages render after answer.
 */
export function MessageList({ turn }: { readonly turn: Turn }) {
  const processMessages = turn.messages.filter(
    (m) => m.kind !== "answer" && m.kind !== "insight",
  );
  const answerMessages = turn.messages.filter((m) => m.kind === "answer");
  const insightMessages = turn.messages.filter((m) => m.kind === "insight");
  const isDone = turn.status !== "running";

  const totalDurationMs =
    turn.completedAt != null ? turn.completedAt - turn.startedAt : undefined;
  const durationText =
    totalDurationMs != null ? formatProcessDuration(totalDurationMs) : undefined;

  return (
    <div className="grid gap-2.5">
      {processMessages.length > 0 && isDone ? (
        <ProcessFold stepCount={processMessages.length} durationText={durationText}>
          {processMessages.map((m) => (
            <MessageRenderer key={m.id} message={m} />
          ))}
        </ProcessFold>
      ) : (
        processMessages.map((m) => <MessageRenderer key={m.id} message={m} />)
      )}

      {answerMessages.map((m) => (
        <MessageRenderer key={m.id} message={m} />
      ))}

      {insightMessages.map((m) => (
        <MessageRenderer key={m.id} message={m} />
      ))}
    </div>
  );
}
