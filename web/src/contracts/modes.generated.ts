/** AUTO-GENERATED — scripts/generate_gateway_contracts.py */

export const ALL_MODES = ['routing', 'consult', 'board', 'pipeline', 'fan_out', 'peer_relay', 'peer_swarm', 'debate', 'graph', 'solo'] as const;
export type Mode = (typeof ALL_MODES)[number];

export const MODE_HELP = {
  routing: "有主导 · Lead 显式委派成员后收口",
  consult: "有主导 · Lead 咨询成员后自己决定",
  board: "有主导 · 全员咨询后 Lead 收口",
  pipeline: "无主导 · 成员顺序接力",
  fan_out: "无主导 · 并行执行再合成",
  peer_relay: "无主导 · 点对点接力",
  peer_swarm: "无主导 · 对等多轮 swarm",
  debate: "无主导 · 多轮辩论",
  graph: "无主导 · 执行图 ENTRY→agents→EXIT",
  solo: "单 Agent（无 Team）",
} as const;

export const MODE_HAS_LEAD = {
  routing: true,
  consult: true,
  board: true,
  pipeline: false,
  fan_out: false,
  peer_relay: false,
  peer_swarm: false,
  debate: false,
  graph: false,
  solo: false,
} as const;

export const EXAMPLE_PROMPTS = {
  routing: ["评估新功能上线的技术风险与业务影响", "制定季度产品路线图的关键里程碑"],
  consult: ["是否应在本周发布灰度版本？", "选择云厂商时应优先考虑哪些因素？"],
  board: ["是否将客服机器人切换到新模型？", "是否批准下一轮融资的使用计划？"],
  pipeline: ["起草并优化一条营销短信", "把用户反馈整理成可执行的行动清单"],
  fan_out: ["从效率、协作、文化三个角度分析远程办公", "并行评估三种技术方案后给出推荐"],
  peer_relay: ["从现象到根因，分析用户登录变慢的问题", "逐步细化一项 MVP 的功能范围"],
  peer_swarm: ["共同拟定一个产品 slogan", "讨论并收敛一份发布检查清单"],
  debate: ["辩论是否应强制双因素认证", "正反方讨论是否采用微服务架构"],
  graph: ["生成一份每日站会议程", "按固定流程完成需求评审摘要"],
  solo: ["用三句话解释这个技术选型的利弊", "帮我列一份决策 checklist"],
} as const;

