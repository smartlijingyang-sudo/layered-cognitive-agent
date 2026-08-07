import { describe, expect, it } from "vitest";
import { renderSequenceDiagram } from "./sequence-diagram";
import type { StampedEvent } from "../contracts/stamped";

describe("sequence diagram", () => {
  it("renders delegation arrows", () => {
    const events: StampedEvent[] = [
      {
        seq: 1,
        ts: 1,
        scope: {
          trace_id: "t",
          run_id: "r",
          parent_run_id: null,
          delegation_id: "d1",
          agent_role: "Lead",
        },
        event: {
          type: "DelegationIssued",
          delegation_id: "d1",
          caller_role: "Lead",
          callee_role: "Alice",
          subtask_preview: "analyze",
          mechanism: "delegate",
          parallel_group: "",
        },
      },
    ];
    const diagram = renderSequenceDiagram(events);
    expect(diagram).toContain("sequenceDiagram");
    expect(diagram).toContain("Lead");
    expect(diagram).toContain("Alice");
  });
});
