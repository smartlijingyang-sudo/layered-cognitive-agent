import { describe, expect, it } from "vitest";
import { isMermaidLanguage, parseCodeLanguage } from "./code-language";

describe("parseCodeLanguage", () => {
  it("extracts language from language-* class", () => {
    expect(parseCodeLanguage("language-python")).toBe("python");
    expect(parseCodeLanguage("language-TSX")).toBe("tsx");
    expect(parseCodeLanguage("language-c++")).toBe("c++");
  });

  it("returns undefined without language class", () => {
    expect(parseCodeLanguage(undefined)).toBeUndefined();
    expect(parseCodeLanguage("")).toBeUndefined();
    expect(parseCodeLanguage("not-a-lang")).toBeUndefined();
  });
});

describe("isMermaidLanguage", () => {
  it("matches mermaid only", () => {
    expect(isMermaidLanguage("mermaid")).toBe(true);
    expect(isMermaidLanguage("python")).toBe(false);
    expect(isMermaidLanguage(undefined)).toBe(false);
  });
});
