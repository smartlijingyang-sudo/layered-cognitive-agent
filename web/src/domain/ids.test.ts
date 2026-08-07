import { describe, expect, it } from "vitest";
import { newLocalId } from "./ids";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

describe("newLocalId", () => {
  it("returns a uuid v4 shaped id", () => {
    expect(newLocalId()).toMatch(UUID_RE);
    expect(newLocalId()).toMatch(UUID_RE);
  });
});
