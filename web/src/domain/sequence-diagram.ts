/** 协作时序图 —— 移植自 sequence_diagram.py，零后端依赖。 */

import type { StampedEvent } from "../contracts/stamped";

const PARTICIPANT_RESERVE = new Set(["team"]);

function alias(role: string): string {
  const cleaned = role.replace(/[^\w-]/g, "_");
  return cleaned || "agent";
}

function participants(events: readonly StampedEvent[]): string[] {
  const seen: string[] = [];
  const add = (role: string) => {
    if (role && !seen.includes(role) && !PARTICIPANT_RESERVE.has(role)) {
      seen.push(role);
    }
  };
  for (const stamped of events) {
    const event = stamped.event;
    if (event.type === "AgentRunStarted") add(event.agent_role);
    if (event.type === "DelegationIssued") {
      add(event.caller_role);
      add(event.callee_role);
    }
  }
  return seen;
}

function callerOf(events: readonly StampedEvent[], delegationId: string): string {
  for (const stamped of events) {
    const event = stamped.event;
    if (event.type === "DelegationIssued" && event.delegation_id === delegationId) {
      return event.caller_role;
    }
  }
  return "";
}

function calleeOf(events: readonly StampedEvent[], delegationId: string): string {
  for (const stamped of events) {
    const event = stamped.event;
    if (event.type === "DelegationIssued" && event.delegation_id === delegationId) {
      return event.callee_role;
    }
  }
  return "";
}

export function renderSequenceDiagram(events: readonly StampedEvent[]): string {
  const issuedTs = new Map<string, number>();
  const arrows: string[] = [];
  let hasDelegation = false;

  for (const stamped of events) {
    const event = stamped.event;
    if (event.type === "DelegationIssued") {
      hasDelegation = true;
      issuedTs.set(event.delegation_id, stamped.ts);
      const arrow = event.mechanism === "handoff" ? "-)>>" : "->>";
      const label = event.subtask_preview || "委派";
      arrows.push(`    ${alias(event.caller_role)}${arrow}${alias(event.callee_role)}: ${label}`);
    } else if (event.type === "DelegationCompleted") {
      const start = issuedTs.get(event.delegation_id);
      const duration = start !== undefined ? `${(stamped.ts - start).toFixed(1)}s` : "";
      const detail = event.status || (event.ok ? "ok" : "failed");
      const suffix = duration ? ` · ${duration}` : "";
      const callee = calleeOf(events, event.delegation_id);
      const caller = callerOf(events, event.delegation_id);
      arrows.push(`    ${alias(callee)}-->>${alias(caller)}: ${detail}${suffix}`);
    }
  }

  if (!hasDelegation) return "";

  const lines = ["sequenceDiagram"];
  for (const role of participants(events)) {
    lines.push(`    participant ${alias(role)} as ${role}`);
  }
  lines.push(...arrows);
  return lines.join("\n");
}
