import { describe, expect, it } from "vitest";
import {
  getToolDisplayName,
  getToolFirstDetail,
  getWorkflowSummaryText,
  parseToolArgs,
} from "./tool-display";
import type { ToolBlock } from "../../projectors/types";

function tool(partial: Partial<ToolBlock> & Pick<ToolBlock, "toolName">): ToolBlock {
  return {
    kind: "tool",
    id: partial.id ?? "t1",
    status: partial.status ?? "done",
    toolName: partial.toolName,
    argumentsPreview: partial.argumentsPreview ?? "",
    resultPreview: partial.resultPreview ?? "",
    invocationId: partial.invocationId ?? "inv1",
    ok: partial.ok,
    latencyMs: partial.latencyMs,
    error: partial.error,
  };
}

describe("tool-display", () => {
  it("maps LCA tools to LobeHub-style verb labels", () => {
    expect(getToolDisplayName("activate_skill")).toBe("启用了技能");
    expect(getToolDisplayName("search_skill")).toBe("搜索了技能");
    expect(getToolDisplayName("sandbox_execute")).toBe("运行了命令");
  });

  it("prefers human description over raw command for detail", () => {
    const detail = getToolFirstDetail(
      tool({
        toolName: "sandbox_execute",
        argumentsPreview: JSON.stringify({
          description: "创建工作目录并安装 docs npm 库",
          code: "npm install docs",
        }),
      }),
    );
    expect(detail).toContain("创建工作目录");
    expect(detail).not.toContain("npm install");
  });

  it("parses args and prefers command when no description", () => {
    const args = parseToolArgs(JSON.stringify({ command: "ls -la", timeout: 30 }));
    expect(args.command).toBe("ls -la");
    const detail = getToolFirstDetail(
      tool({ toolName: "sandbox_execute", argumentsPreview: JSON.stringify(args) }),
    );
    expect(detail).toContain("ls");
  });

  it("builds multi-call summary lead", () => {
    const tools = [
      tool({ id: "a", toolName: "activate_skill" }),
      tool({ id: "b", toolName: "search_skill" }),
      tool({ id: "c", toolName: "sandbox_execute" }),
      tool({ id: "d", toolName: "sandbox_execute" }),
    ];
    const text = getWorkflowSummaryText(tools);
    expect(text).toMatch(/次调用/);
    expect(text).toContain("启用了技能");
    expect(text).toContain("运行了命令");
  });
});
