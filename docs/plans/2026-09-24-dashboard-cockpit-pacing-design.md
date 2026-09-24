# Antigravity Dashboard 单域真值全能驾驶舱与周配额步调设计方案

## 1. 概述与核心愿景 (Overview & Vision)

现有 `agy-monitor-dashboard` 存在 Tab 间功能重叠（任务与矩阵各一套卡片、调度横幅重复）、长文 SOP 视觉噪音过大等问题。
本设计依据业界顶级可观测性看板（Datadog, Vercel, SRE FinOps）标准，全面落地 **单域真值·全能驾驶舱架构 (SSOT Cockpit)**，并引入 **周配额时间步调健康模型 (Weekly Quota Pace & Burn-Rate Index)**。

核心理念：
1. **首页全能 (Cockpit SSOT)**：首页（Tab 1）汇聚 90% 日常核心工作所需（算力总池 + 时间步调 + 智能调度 + 8 账号一体化综合卡片），消灭任何重复卡片。
2. **渐进呈现 (Progressive Disclosure)**：运维长篇 SOP 改造为折叠式手风琴（Accordion），默认收起，点击按需展开。
3. **步调指数 (Weekly Pacing)**：计算实际余量与理论时间消耗水位的偏差（$\Delta = Q_{actual} - Q_{expected}$），直观反映配额是透支超速还是充沛富余。

## 2. 核心责任边界 (Scope Boundaries)

- **Owns (本次构建与优化的范围)**:
  1. **周配额步调算法**: 在 `app.py` 中根据 `resetTime` 动态计算各账号及全集群的理论时间基准余量、步调偏差 $\Delta$ 及快慢状态。
  2. **Tab 体系彻底收敛 (4 Tab -> 3 Tab)**:
     - Tab 1: **【驾驶舱总览 (Cockpit)】**（集成算力池、时间步调健康度、智能调度、8 账号全能卡片）；
     - Tab 2: **【数据洞察 (Analytics)】**（保持纯粹的图表与统计分析）；
     - Tab 3: **【运维中心 (Operations)】**（顶部会话管理 + 4 个折叠式手风琴 SOP 面板）。
  3. **8 账号一体化卡片 (SSOT)**: 垂直融合同一账号的身份、心跳、5h双环、周配额及步调偏差、实时活动/Prompt 摘要、一键终端与管理命令。
  4. **全集群宏观步调条**: 顶部清晰展示全集群 Gemini 与 Claude 相对时间进度的超速/落后百分比。

- **Does NOT own (严格禁止触碰与修改的范围)**:
  - 不修改任何 Google OAuth 底层凭据体系与本地隔离 HOME 目录。
  - 不引入任何外部 CDN，保持 100% 离线高可用。
  - 不修改 `layered-cognitive-agent` 核心框架协议。

## 3. 自动化定级 (Autopilot Ladder)

- **定级**: `DRAFT`（独立运维看板重构与算法增补，低爆炸半径）。

## 4. 数学模型与数据契约 (Mathematical Pacing Contract)

### 4.1 单账号周时间步调公式
- 周期：$T_{cycle} = 168 \text{ 小时}$。
- 剩余时间：$h_{rem} = \max(0, \min(168, (\text{resetTime} - \text{now}).\text{total\_seconds}() / 3600))$。
- 理论应剩比例：$Q_{exp} = \frac{h_{rem}}{168} \times 100\%$。
- 步调偏差：$\Delta = Q_{act} - Q_{exp}$。
  - $\Delta \ge 0$：🟢 消耗慢于时间流速（余量充沛安全，如 $+15.2\%$）
  - $-15\% \le \Delta < 0$：🟡 消耗稍快于时间流速
  - $\Delta < -15\%$：🔴 严重超速透支（有提前耗尽风险）

### 4.2 `/api/quota` 响应契约扩充

```json
{
  "status": "ok",
  "aggregate": {
    "gemini_weekly_avg": 73.5,
    "gemini_expected_avg": 42.8,
    "gemini_pacing_delta": 30.7,
    "claude_weekly_avg": 76.8,
    "claude_expected_avg": 42.8,
    "claude_pacing_delta": 34.0,
    "healthy_accounts": 8,
    "total_accounts": 8
  },
  "quotas": {
    "a": {
      "account_id": "a",
      "available": true,
      "gemini_weekly": 48.2,
      "gemini_pacing": {
        "expected_percent": 42.8,
        "delta": 5.4,
        "status": "HEALTHY",
        "remaining_hours": 72.0
      },
      "claude_weekly": 29.5,
      "claude_pacing": {
        "expected_percent": 42.8,
        "delta": -13.3,
        "status": "WARNING",
        "remaining_hours": 72.0
      }
    }
  }
}
```

## 5. UI 架构与折叠机制

- **首页 (Tab 1: Cockpit)**：
  - [全集群算力与时间步调总池] -> 宏观柱形条 + 时间步调偏差标签；
  - [极简智能调度条] -> 仅保留最优账号快速切换与 Prompt 快速发送；
  - [8 账号全能卡片网格] -> 消除一切重复卡片。
- **运维中心 (Tab 3: Operations)**：
  - 4 个 `<details class="glass-card">` 折叠面板：
    1. 事故复盘与 Session Expired 防废号铁律
    2. 异地风控与 Google Cloud Shell 信任初始化
    3. Google AI Pro 订阅与未成年排查
    4. 新账号接入与快速克隆 SOP
