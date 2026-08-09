import { describe, expect, it } from "vitest";
import { extractUserFacingAnswer, sanitizeAssistantDisplayText } from "./extract-decision-text";

const SAMPLE =
  '{ "action_type": "respond", "response_text": "作为运营经理，我将从效率、协作、文化三个维度分析。\\n\\n✅ 一、效率维度\\n- 核心矛盾：个体产出易量化。" }';

const PSEUDO_TOOL_SAMPLE = JSON.stringify({
  action_type: "use_tool",
  tool_name: "respond",
  arguments: {
    response_text: "根据文件预览分析，我发现了一个问题。",
    rationale: "文件是 HTML",
    confidence: "0.95",
  },
  rationale: "json wrap",
});

describe("extractUserFacingAnswer", () => {
  it("extracts response_text from complete decision JSON", () => {
    const text = extractUserFacingAnswer(SAMPLE);
    expect(text).toContain("作为运营经理");
    expect(text).toContain("✅ 一、效率维度");
    expect(text).not.toContain("action_type");
  });

  it("hoists response_text from use_tool(respond) arguments (shape mirror)", () => {
    const text = extractUserFacingAnswer(PSEUDO_TOOL_SAMPLE);
    expect(text).toBe("根据文件预览分析，我发现了一个问题。");
    expect(text).not.toContain("action_type");
    expect(text).not.toContain("use_tool");
  });

  it("extracts partial response_text during streaming", () => {
    const partial = '{ "action_type": "respond", "response_text": "作为运营经理，我将';
    const text = extractUserFacingAnswer(partial, { allowPartial: true });
    expect(text).toBe("作为运营经理，我将");
  });

  it("returns null for non-decision text", () => {
    expect(extractUserFacingAnswer("普通 Markdown 段落")).toBeNull();
  });
});

describe("sanitizeAssistantDisplayText", () => {
  it("sanitizes JSON blobs for display", () => {
    const out = sanitizeAssistantDisplayText(SAMPLE);
    expect(out).toContain("作为运营经理");
    expect(out).not.toContain("{");
  });

  it("sanitizes pseudo-tool respond JSON", () => {
    const out = sanitizeAssistantDisplayText(PSEUDO_TOOL_SAMPLE);
    expect(out).toContain("根据文件预览分析");
    expect(out).not.toContain("use_tool");
  });

  it("passes through normal markdown", () => {
    const md = "## 标题\n\n正文";
    expect(sanitizeAssistantDisplayText(md)).toBe(md);
  });
});
