import type { StampedEvent } from "../contracts/stamped";
import {
  EMPTY_TRACE_STATE,
  type RunInfo,
  type TraceState,
  type Verbosity,
  shouldShowEvent,
} from "./types";

function cloneRuns(runs: TraceState["runs"]): Map<string, RunInfo> {
  return new Map(runs);
}

/** 镜像 ConsoleJournalProjector._TraceState 的前端归约器。 */
export function reduceTrace(state: TraceState, stamped: StampedEvent): TraceState {
  const e = stamped.event;
  const runs = cloneRuns(state.runs);

  switch (e.type) {
    case "TeamRunStarted":
      return {
        ...state,
        teamRun: {
          teamId: e.team_id,
          mandate: e.mandate,
          members: [...e.members],
          objectivePreview: e.objective_preview,
        },
        runs: new Map(runs).set(stamped.scope.run_id, {
          runId: stamped.scope.run_id,
          role: "(team)",
        }),
      };
    case "TeamRunFinished":
      return { ...state, status: e.status };
    case "AgentRunStarted": {
      const next = new Map(runs);
      next.set(stamped.scope.run_id, {
        runId: stamped.scope.run_id,
        role: e.agent_role,
      });
      return { ...state, runs: next };
    }
    case "AgentRunFinished": {
      const prev = runs.get(stamped.scope.run_id);
      const next = new Map(runs);
      next.set(stamped.scope.run_id, {
        runId: stamped.scope.run_id,
        role: prev?.role ?? stamped.scope.agent_role,
        status: e.status,
        steps: e.steps,
        llmCalls: prev?.llmCalls,
        toolCalls: prev?.toolCalls,
      });
      return { ...state, runs: next };
    }
    case "DelegationIssued":
      return { ...state, delegations: [...state.delegations, e] };
    case "DelegationCompleted":
      return state;
    case "DecisionMade":
      return { ...state, decisions: [...state.decisions, e] };
    case "ToolInvoked": {
      const prev = runs.get(stamped.scope.run_id);
      const next = new Map(runs);
      if (prev) {
        next.set(stamped.scope.run_id, {
          ...prev,
          toolCalls: (prev.toolCalls ?? 0) + 1,
        });
      }
      return { ...state, runs: next, toolCalls: [...state.toolCalls, e] };
    }
    case "LlmCallCompleted": {
      const prev = runs.get(stamped.scope.run_id);
      const next = new Map(runs);
      if (prev) {
        next.set(stamped.scope.run_id, {
          ...prev,
          llmCalls: (prev.llmCalls ?? 0) + 1,
        });
      }
      return { ...state, runs: next, llmCalls: [...state.llmCalls, e] };
    }
    case "RunInsight":
      return { ...state, insights: [...state.insights, e] };
    case "SynthesisCompleted":
      return { ...state, synthesisText: e.output_text };
    default:
      return state;
  }
}

export function buildTraceState(
  events: readonly StampedEvent[],
  verbosity: Verbosity = "standard",
): TraceState {
  return events.reduce((acc, stamped) => {
    if (!shouldShowEvent(stamped.event.type, verbosity)) return acc;
    return reduceTrace(acc, stamped);
  }, EMPTY_TRACE_STATE);
}

export class TraceProjector {
  private state: TraceState = EMPTY_TRACE_STATE;

  constructor(private readonly verbosity: Verbosity = "standard") {}

  onEvent(stamped: StampedEvent): TraceState {
    if (!shouldShowEvent(stamped.event.type, this.verbosity)) return this.state;
    this.state = reduceTrace(this.state, stamped);
    return this.state;
  }

  snapshot(): TraceState {
    return this.state;
  }

  reset(): void {
    this.state = EMPTY_TRACE_STATE;
  }
}
