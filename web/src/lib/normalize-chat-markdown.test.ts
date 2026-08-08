import { describe, expect, it } from "vitest";
import { normalizeChatMarkdown } from "./normalize-chat-markdown";

describe("normalizeChatMarkdown", () => {
  it("merges short plain paragraphs separated by blank lines", () => {
    const input = "第一句。\n\n第二句。\n\n第三句。";
    expect(normalizeChatMarkdown(input)).toBe("第一句。 第二句。 第三句。");
  });

  it("preserves code fences", () => {
    const input = "说明文字\n\n```python\nprint(1)\n```\n\n结尾";
    expect(normalizeChatMarkdown(input)).toContain("```python");
    expect(normalizeChatMarkdown(input)).toMatch(/说明文字[\s\S]*结尾/);
  });

  it("preserves headings and lists", () => {
    const input = "## 标题\n\n- 项一\n- 项二";
    expect(normalizeChatMarkdown(input)).toBe(input);
  });

  it("bolds list labels before colon", () => {
    const input = "- 核心矛盾：个体产出易量化\n- 关键抓手：对齐机制";
    const out = normalizeChatMarkdown(input);
    expect(out).toContain("**核心矛盾：**");
    expect(out).toContain("**关键抓手：**");
  });
});
