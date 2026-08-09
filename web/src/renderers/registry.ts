import type { JournalEventType } from "../contracts";
import { JOURNAL_EVENT_TYPES } from "../contracts";
import {
  CastingCompletedCard,
  CastingFailedCard,
  CastingStartedCard,
  ContainerCard,
  DecisionCard,
  DelegationCard,
  DelegationCompletedCard,
  InsightBadge,
  LlmCallCard,
  ReasoningCompletedCard,
  ReasoningDeltaCard,
  SandboxOutputDeltaCard,
  StepTextDeltaCard,
  SynthesisCard,
  ToolCallCard,
  ToolStartedCard,
  type EventRenderer,
} from "./event-cards";

/** 事件类型 → 渲染组件登记表（与 JOURNAL_EVENT_CLASSES 对称）。 */
export const EVENT_RENDERERS: Record<JournalEventType, EventRenderer> = {
  CastingStarted: CastingStartedCard,
  CastingCompleted: CastingCompletedCard,
  CastingFailed: CastingFailedCard,
  TeamRunStarted: ContainerCard,
  TeamRunFinished: ContainerCard,
  AgentRunStarted: ContainerCard,
  AgentRunFinished: ContainerCard,
  DelegationIssued: DelegationCard,
  DelegationCompleted: DelegationCompletedCard,
  DelegationCacheHit: ContainerCard,
  SynthesisCompleted: SynthesisCard,
  DecisionMade: DecisionCard,
  StepCompleted: ContainerCard,
  ActionDegraded: ContainerCard,
  LlmCallCompleted: LlmCallCard,
  StepTextDelta: StepTextDeltaCard,
  ReasoningDelta: ReasoningDeltaCard,
  ReasoningCompleted: ReasoningCompletedCard,
  SandboxOutputDelta: SandboxOutputDeltaCard,
  ToolStarted: ToolStartedCard,
  ToolInvoked: ToolCallCard,
  ToolDenied: ContainerCard,
  RunInsight: InsightBadge,
};

export function assertRendererCoverage(): void {
  const keys = new Set(Object.keys(EVENT_RENDERERS));
  for (const name of JOURNAL_EVENT_TYPES) {
    if (!keys.has(name)) {
      throw new Error(`Missing renderer for ${name}`);
    }
  }
}

export { JOURNAL_EVENT_TYPES };
