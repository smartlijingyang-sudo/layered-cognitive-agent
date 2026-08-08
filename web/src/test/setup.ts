import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

/** jsdom lacks SVG geometry APIs that mermaid uses during layout. */
function polyfillSvgGeometry(): void {
  const bbox = { x: 0, y: 0, width: 100, height: 20, top: 0, left: 0, right: 100, bottom: 20 };
  const proto =
    typeof SVGElement !== "undefined"
      ? SVGElement.prototype
      : (globalThis as { SVGElement?: { prototype: object } }).SVGElement?.prototype;
  if (!proto) return;

  const target = proto as unknown as {
    getBBox?: () => typeof bbox;
    getComputedTextLength?: () => number;
    getScreenCTM?: () => DOMMatrix | null;
  };

  if (typeof target.getBBox !== "function") {
    target.getBBox = () => bbox;
  }
  if (typeof target.getComputedTextLength !== "function") {
    target.getComputedTextLength = () => 100;
  }
}

polyfillSvgGeometry();

// Some mermaid paths touch createSVGPoint
if (typeof SVGSVGElement !== "undefined") {
  const svgProto = SVGSVGElement.prototype as unknown as {
    createSVGPoint?: () => { x: number; y: number; matrixTransform: () => { x: number; y: number } };
  };
  if (typeof svgProto.createSVGPoint !== "function") {
    svgProto.createSVGPoint = () => ({
      x: 0,
      y: 0,
      matrixTransform: () => ({ x: 0, y: 0 }),
    });
  }
}
