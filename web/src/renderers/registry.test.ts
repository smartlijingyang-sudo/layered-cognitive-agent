import { describe, expect, it } from "vitest";
import { assertRendererCoverage, EVENT_RENDERERS } from "./registry";
import { JOURNAL_EVENT_TYPES } from "../contracts";

describe("renderer coverage", () => {
  it("covers all journal event types", () => {
    expect(() => assertRendererCoverage()).not.toThrow();
    expect(Object.keys(EVENT_RENDERERS).sort()).toEqual([...JOURNAL_EVENT_TYPES].sort());
  });
});
