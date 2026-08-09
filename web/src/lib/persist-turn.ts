import type { StampedEvent } from "../contracts";
import { USER_FACING_TERMINAL_ACTIONS } from "../projectors/message-projector";

/** 语义边界：此时 answer/status 变更应落盘 IndexedDB，而非仅更新内存。 */
export function shouldPersistTurnOnEvent(stamped: StampedEvent): boolean {
  const event = stamped.event;
  switch (event.type) {
    case "DecisionMade":
      return USER_FACING_TERMINAL_ACTIONS.has(event.action_type);
    case "TeamRunFinished":
    case "AgentRunFinished":
    case "SynthesisCompleted":
    case "CastingFailed":
      return true;
    default:
      return false;
  }
}
