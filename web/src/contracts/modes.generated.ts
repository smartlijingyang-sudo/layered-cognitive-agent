/** AUTO-GENERATED — scripts/generate_gateway_contracts.py */

export const ALL_MODES = ['solo', 'team'] as const;
export type Mode = (typeof ALL_MODES)[number];

export const SOLO_MODE_KEY = "solo";

export const MODE_HELP = {
  team: "团队 · 系统按任务自动组队和分工",
  solo: "",
} as const;

export const EXAMPLE_PROMPTS = {
  team: ["给新功能写发布文案并评估技术风险", "制定季度产品路线图的关键里程碑", "从效率、协作、文化三个角度分析远程办公", "是否应在本周发布灰度版本？"],
  solo: [],
} as const;

