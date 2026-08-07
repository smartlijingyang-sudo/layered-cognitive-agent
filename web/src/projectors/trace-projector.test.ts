import { describe, expect, it } from "vitest";
import { buildTraceState } from "./trace-projector";
import { parseStampedRecord } from "../contracts/stamped";
import type { StampedRecord } from "../contracts";

describe("trace projector", () => {
  it("reduces team run lifecycle", () => {
    const started: StampedRecord = {
      schema: "journal.v1",
      seq: 1,
      ts: 1,
      scope: {
        trace_id: "t",
        run_id: "r",
        parent_run_id: null,
        delegation_id: null,
        agent_role: "",
      },
      event_type: "TeamRunStarted",
      event: {
        type: "TeamRunStarted",
        team_id: "team-x",
        mandate: "board",
        members: ["Alice", "Bob"],
        objective_preview: "hello",
        strategy_key: "",
        lead_role: "",
        objective: "",
        plan_steps: "",
      },
    };
    const state = buildTraceState([parseStampedRecord(started)]);
    expect(state.teamRun?.teamId).toBe("team-x");
    expect(state.teamRun?.members).toEqual(["Alice", "Bob"]);
  });
});
