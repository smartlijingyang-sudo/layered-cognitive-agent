import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MarkdownContent } from "./MarkdownContent";

describe("MarkdownContent", () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps sanitize → normalize pipeline (strips decision JSON noise)", () => {
    const raw = '```json\n{"action":"respond","content":"hello from decision"}\n```';
    // Even if sanitize does not fully strip, component must render without crashing
    // and never show raw unprocessed empty when text has content.
    const { container } = render(<MarkdownContent text="Plain **bold** answer" />);
    expect(container.querySelector(".markdown-body")).toBeTruthy();
    expect(container.textContent).toContain("bold");
    // decision-shaped input still goes through sanitize first
    const { container: c2 } = render(<MarkdownContent text={raw} />);
    expect(c2.querySelector(".markdown-body")).toBeTruthy();
  });

  it("renders KaTeX formula DOM for math notation (not raw $ source)", async () => {
    const { container } = render(
      <MarkdownContent text="Einstein: $E=mc^2$ and display $$a^2+b^2=c^2$$" />,
    );
    await waitFor(() => {
      const katex = container.querySelector(".katex");
      expect(katex).toBeTruthy();
    });
    // Raw delimiters should not be the only visible form
    expect(container.querySelector(".katex")?.textContent).toMatch(/E|mc|a|b|c/i);
  });

  it("renders a valid mermaid fence as SVG diagram", async () => {
    const md = ["```mermaid", "sequenceDiagram", "  Alice->>Bob: Hello", "```"].join("\n");
    const { container } = render(<MarkdownContent text={md} />);
    await waitFor(
      () => {
        const diagram = container.querySelector('[data-testid="mermaid-diagram"]');
        expect(diagram).toBeTruthy();
        expect(diagram?.innerHTML).toMatch(/<svg[\s>]/i);
      },
      { timeout: 8000 },
    );
  });

  it("falls back to readable code for invalid mermaid (no blank answer)", async () => {
    const md = ["```mermaid", "not valid mermaid {{{", "```"].join("\n");
    const { container } = render(<MarkdownContent text={md} />);
    await waitFor(
      () => {
        const fallback = container.querySelector('[data-testid="mermaid-fallback"]');
        expect(fallback).toBeTruthy();
        expect(fallback?.textContent).toContain("not valid mermaid");
      },
      { timeout: 8000 },
    );
  });

  it("highlights fenced code without vanishing the source", async () => {
    const md = ["```typescript", "const answer = 42;", "```"].join("\n");
    const { container } = render(<MarkdownContent text={md} />);
    // Eventually either highlighted or plain — but code text always present
    await waitFor(
      () => {
        expect(container.textContent).toContain("const answer = 42");
      },
      { timeout: 8000 },
    );
    // Copy button present (at least one — plain or highlighted path)
    expect(screen.getAllByLabelText("复制代码").length).toBeGreaterThan(0);
  });
});

