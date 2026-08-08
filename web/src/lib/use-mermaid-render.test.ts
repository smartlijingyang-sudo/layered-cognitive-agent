import { describe, expect, it } from "vitest";
import { renderMermaidSvg } from "./use-mermaid-render";

describe("renderMermaidSvg", () => {
  it("renders a valid sequence diagram to SVG markup", async () => {
    const source = "sequenceDiagram\n  A->>B: hi";
    const svg = await renderMermaidSvg(source, `test-valid-${Date.now()}`);
    expect(svg).toMatch(/<svg[\s>]/i);
  });

  it("rejects invalid mermaid so callers can fall back", async () => {
    await expect(
      renderMermaidSvg("this is not mermaid {{{", `test-invalid-${Date.now()}`),
    ).rejects.toBeTruthy();
  });
});
