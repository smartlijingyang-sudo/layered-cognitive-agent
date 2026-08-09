import { clampMenuPoint, type MenuPoint } from "../../lib/clamp-menu-position";
import { COMPOSER_MENU_SIDE_OFFSET } from "./composer-menu";

/** LobeHub ActionBar: top at chat dock, bottom on home input. */
export type ComposerMenuPlacement = "topLeft" | "bottomLeft";

export interface MenuPlacementStyle extends MenuPoint {
  readonly transform?: string;
}

const DEFAULT_MENU_WIDTH = 220;
const DEFAULT_MENU_HEIGHT = 44;

/** Place popup above/below trigger — transform avoids height measurement drift. */
export function computeMainMenuStyle(
  anchor: DOMRect,
  placement: ComposerMenuPlacement,
  size: { readonly width: number; readonly height: number } = {
    width: DEFAULT_MENU_WIDTH,
    height: DEFAULT_MENU_HEIGHT,
  },
): MenuPlacementStyle {
  const left = anchor.left;

  if (placement === "topLeft") {
    const visualTop = anchor.top - COMPOSER_MENU_SIDE_OFFSET - size.height;
    const clamped = clampMenuPoint({ left, top: visualTop }, size);
    const top = clamped.top + size.height;
    return {
      left: clamped.left,
      top,
      transform: "translateY(-100%)",
    };
  }

  const top = anchor.bottom + COMPOSER_MENU_SIDE_OFFSET;
  return clampMenuPoint({ left, top }, size);
}
