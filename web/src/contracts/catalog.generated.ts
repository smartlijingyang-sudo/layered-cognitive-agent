/** AUTO-GENERATED — scripts/generate_ui_catalog.py */

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

export const MODE_DEFAULT_OBJECTIVE = {
  routing: "你是项目 Lead。任务：评估「移动端新功能上线」的风险。必须先分别委派：Alice 做技术风险（一句话），Bob 做业务风险（一句话）；等他们返回后，你再汇总成 3 条结论。禁止自己直接答完、禁止反问。",
  consult: "你是决策 Lead。问题：我们是否应该本周发布灰度？请先向 Alice 和 Bob 各征求一句意见，再由你本人给出「发布/暂缓」结论和理由。禁止只反问用户。",
  board: "董事会场景：是否把客服机器人切换到新模型？请 Alice 给「支持」理由一句，Bob 给「风险」一句；Lead 综合后给出最终决议（通过/否决）和一句总结。禁止反问。",
  pipeline: "流水线任务：写一条「周末大促」短信文案。Alice 先写草稿（一句），Bob 改得更有转化力（一句），Carol 输出最终可发送版本（一句）。每人只做自己那一棒。",
  fan_out: "并行调研：关于「远程办公」各给一个观点——Alice 从效率、Bob 从协作、Carol 从文化；最后合成三条要点。每人一句，禁止反问。",
  peer_relay: "接力任务：把「用户登录慢」从现象拆到可能原因。Alice 先写现象与假设（一句），Bob 在其基础上给出最可能原因（一句）。简洁，禁止反问。",
  peer_swarm: "两人对等讨论：产品 slogan 候选。Alice 提一个 slogan，Bob 提改进；各一轮后给出你们共同认可的最终 slogan（一句）。禁止反问。",
  debate: "辩论题：是否应强制双因素认证。Alice 支持强制，Bob 反对强制；各陈述一句后给出一个折中建议（一句）。禁止反问。",
  graph: "图执行任务：生成「每日站会」议程。Alice 列出 3 个议题关键词，Bob 整理成一句可宣读的议程。禁止反问。",
  solo: "用一句话自我介绍，并说明你理解到的任务是「solo 模式探针」。直接回答，不要反问，不要超过两句。",
} as const;

export type RunStatus = "pending" | "running" | "completed" | "failed" | "canceled";

export interface CreateRunRequest {
  readonly question: string;
  readonly mode: string;
  readonly track: unknown;
}

export interface CreateRunResponse {
  readonly run_id: string;
  readonly trace_id: string;
}

