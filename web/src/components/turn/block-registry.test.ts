import { describe, expect, it } from "vitest";
import { partitionProcessSegments } from "./block-registry";
import type { ThinkingBlock, ToolBlock, TurnProcessBlock } from "../../projectors/types";

function tool(id: string, name = "sandbox_execute"): ToolBlock {
  return {
    kind: "tool",
    id,
    status: "done",
    toolName: name,
    argumentsPreview: "{}",
    resultPreview: "ok",
    invocationId: id,
  };
}

function thinking(): ThinkingBlock {
  return {
    kind: "thinking",
    id: "th1",
    status: "done",
    content: "…",
    durationMs: 1200,
  };
}

describe("partitionProcessSegments", () => {
  it("keeps single tool inline", () => {
    const blocks: TurnProcessBlock[] = [thinking(), tool("t1")];
    const segs = partitionProcessSegments(blocks);
    expect(segs.every((s) => s.kind === "single")).toBe(true);
  });

  it("folds multi-tool cluster into workflow", () => {
    const blocks: TurnProcessBlock[] = [
      thinking(),
      tool("t1", "search_skill"),
      tool("t2", "activate_skill"),
      tool("t3", "sandbox_execute"),
    ];
    const segs = partitionProcessSegments(blocks);
    expect(segs.some((s) => s.kind === "workflow")).toBe(true);
    const wf = segs.find((s) => s.kind === "workflow");
    if (wf?.kind === "workflow") {
      expect(wf.tools).toHaveLength(3);
      expect(wf.thinkingMs).toBe(1200);
    }
  });
});
