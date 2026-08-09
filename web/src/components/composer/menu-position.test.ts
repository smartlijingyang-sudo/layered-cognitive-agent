import { describe, expect, it } from "vitest";
import { computeMainMenuStyle } from "./menu-position";

describe("computeMainMenuStyle", () => {
  const anchor = {
    left: 100,
    top: 500,
    right: 132,
    bottom: 532,
    width: 32,
    height: 32,
    x: 100,
    y: 500,
    toJSON: () => ({}),
  } as DOMRect;

  it("opens above trigger on topLeft with translateY(-100%)", () => {
    const style = computeMainMenuStyle(anchor, "topLeft", {
      width: 220,
      height: 44,
    });
    expect(style.left).toBe(100);
    expect(style.top).toBe(500 - 8);
    expect(style.transform).toBe("translateY(-100%)");
  });

  it("opens below trigger on bottomLeft", () => {
    const style = computeMainMenuStyle(anchor, "bottomLeft", {
      width: 220,
      height: 44,
    });
    expect(style.top).toBe(532 + 8);
    expect(style.left).toBe(100);
    expect(style.transform).toBeUndefined();
  });
});
