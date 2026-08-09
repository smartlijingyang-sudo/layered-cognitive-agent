import { describe, expect, it } from "vitest";
import { submenuPoint } from "./clamp-menu-position";

describe("submenuPoint", () => {
  it("flips submenu to the left when right edge would overflow", () => {
    const rect = {
      left: 900,
      right: 1100,
      top: 400,
      bottom: 440,
      width: 200,
      height: 40,
      x: 900,
      y: 400,
      toJSON: () => ({}),
    } as DOMRect;
    Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
    const point = submenuPoint(rect, 260, 8);
    expect(point.left).toBeLessThan(rect.left);
  });
});
