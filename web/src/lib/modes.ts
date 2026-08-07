import {
  ALL_MODES,
  AUTO_MODE_HELP,
  AUTO_MODE_KEY,
  MODE_HELP,
  type Mode,
} from "../contracts/modes.generated";

export { AUTO_MODE_KEY, AUTO_MODE_HELP };

export const MODE_LABELS: Record<Mode, string> = {
  routing: "routing · 委派收口",
  consult: "consult · 咨询决策",
  board: "board · 全员咨询",
  pipeline: "pipeline · 顺序接力",
  fan_out: "fan_out · 并行合成",
  peer_relay: "peer_relay · 点对点接力",
  peer_swarm: "peer_swarm · 对等 swarm",
  debate: "debate · 多轮辩论",
  graph: "graph · 执行图",
  solo: "solo · 单 Agent",
};

export function modeLabel(mode: string): string {
  if (mode === AUTO_MODE_KEY) return "智能组队";
  if (mode in MODE_LABELS) return MODE_LABELS[mode as Mode];
  return mode;
}

export function modeHelp(mode: string): string {
  if (mode === AUTO_MODE_KEY) return AUTO_MODE_HELP;
  if (mode in MODE_HELP) return MODE_HELP[mode as Mode];
  return "选择协作模式";
}

export function isKnownMode(mode: string): boolean {
  return mode === AUTO_MODE_KEY || (ALL_MODES as readonly string[]).includes(mode);
}
