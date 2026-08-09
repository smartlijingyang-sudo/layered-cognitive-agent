/** Keep fixed-position menus inside the viewport. */

export interface MenuPoint {
  readonly left: number;
  readonly top: number;
}

export interface MenuSize {
  readonly width: number;
  readonly height: number;
}

const VIEWPORT_PAD = 8;

export function clampMenuPoint(
  point: MenuPoint,
  size: MenuSize,
  viewport = { width: window.innerWidth, height: window.innerHeight },
): MenuPoint {
  const maxLeft = Math.max(VIEWPORT_PAD, viewport.width - size.width - VIEWPORT_PAD);
  const maxTop = Math.max(VIEWPORT_PAD, viewport.height - size.height - VIEWPORT_PAD);
  return {
    left: Math.min(Math.max(VIEWPORT_PAD, point.left), maxLeft),
    top: Math.min(Math.max(VIEWPORT_PAD, point.top), maxTop),
  };
}

/** Prefer opening to the right; flip left when it would overflow. */
export function submenuPoint(
  anchorRect: DOMRect,
  submenuWidth: number,
  gap = 8,
): MenuPoint {
  const right = anchorRect.right + gap;
  const leftFlip = anchorRect.left - gap - submenuWidth;
  const left =
    right + submenuWidth > window.innerWidth - VIEWPORT_PAD && leftFlip >= VIEWPORT_PAD
      ? leftFlip
      : right;
  return { left, top: anchorRect.top };
}
