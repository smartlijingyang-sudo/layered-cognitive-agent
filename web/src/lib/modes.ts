import {
  ALL_MODES,
  MODE_HELP,
  SOLO_MODE_KEY,
  type Mode,
} from "../contracts/modes.generated";

export { SOLO_MODE_KEY };

const MODE_LABELS: Record<Mode, string> = {
  solo: "直接问",
  team: "组队做",
};

export function modeLabel(mode: string): string {
  if (mode in MODE_LABELS) return MODE_LABELS[mode as Mode];
  return mode;
}

export function modeHelp(mode: string): string {
  if (mode === SOLO_MODE_KEY) return "系统直接回答，不组队";
  if (mode in MODE_HELP) return MODE_HELP[mode as Mode];
  return "选择协作模式";
}

export function isKnownMode(mode: string): boolean {
  return (ALL_MODES as readonly string[]).includes(mode);
}
