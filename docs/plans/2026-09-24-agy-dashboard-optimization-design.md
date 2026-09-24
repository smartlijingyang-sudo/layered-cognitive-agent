# Antigravity Dashboard 优化升级设计方案 (DevOps 沉浸流)

## 1. 概述与背景 (Overview & Context)

本项目为 `agy-monitor-dashboard`（基于 FastAPI + Vue 3 + Tailwind CSS）的体验优化升级。
在调研 [sindresorhus/awesome](https://github.com/sindresorhus/awesome) 优质自托管及监控生态（如 Uptime Kuma、Glance、Beszel、Homepage 等）后，针对现有监控看板信息层次扁平、无历史心跳感知、缺乏全局算力总览等痛点，落地 **方案 A：轻量沉浸运维流 (DevOps & Status)**。

## 2. 核心责任边界 (Scope Boundaries)

- **Owns (本次构建与优化的范围)**:
  1. **集群总算力与配额聚合池 (Cluster Resource Pool)**: 实时聚合 8 个活跃账号（A, B, C, E, F, I, J, K）的 Gemini 与 Claude 3P 配额总余量与比例。
  2. **Uptime 心跳健康微条 (Heartbeat Bar)**: 账号卡片展示最近 20 次探测的连通性小方块，附带响应耗时 (ms) 与健康状态 Tooltip。
  3. **紧凑双层圆环仪表 (Dual-Ring Quota Gauges)**: 基于轻量原生 SVG 打造 Gemini 与 Claude 5小时限制的圆环微图表，自适应阈值着色。
  4. **极客全局快捷键系统 (Keyboard Shortcuts)**: 支持 `1-4` 键快速无缝切页、`R` 键强制全量刷新、`Cmd+K`/`Ctrl+K` 聚焦卡片过滤检索。
  5. **一键复制与微动效 (Quick Copy & Micro-interactions)**: 对 `agy-x` 命令与 tmux 挂载指令提供 1-click 拷贝、打勾动效与轻量 Toast 提醒。
  6. **轻量心跳历史收集**: 后端 `app.py` 内存中滚动维护最近 20 次探测数据，无额外数据库负担。

- **Does NOT own (严格禁止触碰与修改的范围)**:
  - 严禁触碰任何账号的 Google OAuth 凭据体系与账户隔离机制。
  - 严禁修改 `layered-cognitive-agent` 核心代码库的任何协议与业务逻辑。
  - 严禁引入任何外网 CDN 资源，确保 100% 局域网离线高可用。

## 3. 自动化定级 (Autopilot Ladder)

- **定级**: `DRAFT`
  - 属于辅助工具集与运维看板层面的前端交互与展示增强，低爆炸半径，不影响核心 Agent 生产链路。

## 4. UI/UX 布局与交互体系

```
+-----------------------------------------------------------------------------------------------+
|  ⚡ Antigravity Cluster Hub      [1:任务 2:矩阵 3:分析 4:SOP] [R:刷新] [Cmd+K:搜索]  (15s倒计时) |
+-----------------------------------------------------------------------------------------------+
|  📊 集群总算力与配额聚合池 (Cluster Resource Pool)                                             |
|  ├─ Gemini 总体余量:  [██████████████████░░░] 68.4% (547% / 800% Pool)  - 充裕状态            |
|  └─ Claude 3P总体余量: [████████████████░░░░░] 61.2% (490% / 800% Pool)  - 充裕状态            |
+-----------------------------------------------------------------------------------------------+
|  🖥️ 账号矩阵卡片 (Enhanced Cards with Heartbeat & Dual-Ring)                                  |
|  +-------------------------------------------+  +-------------------------------------------+ |
|  | 账号 A (kuaikuaibaby)  [运行中] [老号通用] |  | 账号 B (smartlijingyang) [运行中] [基准]  | |
|  | 心跳: 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 (120ms)|  | 心跳: 🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩 (98ms) | |
|  | [ 双层环形仪表 ]   Gemini:  周 48% | 5h 99% |  | [ 双层环形仪表 ]   Gemini:  周  3% | 5h 85% | |
|  |   ◎  ◎           Claude:  周 30% | 5h 100%|  |   ◎  ◎           Claude:  周 34% | 5h 100%| |
|  | [复制: agy-a 📋] [复制: tmux挂载 📋]      |  | [复制: agy-b 📋] [复制: tmux挂载 📋]      | |
|  +-------------------------------------------+  +-------------------------------------------+ |
+-----------------------------------------------------------------------------------------------+
```

## 5. 接口与数据契约 (API & Data Flow)

### 5.1 `/api/quota` 响应契约扩充

```json
{
  "status": "ok",
  "cached": false,
  "updated_at": 1790256800.0,
  "aggregate": {
    "gemini_weekly_avg": 68.4,
    "gemini_weekly_total": 547.2,
    "claude_weekly_avg": 61.2,
    "claude_weekly_total": 489.6,
    "healthy_accounts": 8,
    "total_accounts": 8
  },
  "quotas": {
    "a": {
      "account_id": "a",
      "available": true,
      "gemini_weekly": 48.2,
      "gemini_5h": 99.4,
      "claude_weekly": 29.5,
      "claude_5h": 100.0,
      "heartbeats": [
        {"ts": 1790256600, "ok": true, "latency_ms": 128},
        {"ts": 1790256615, "ok": true, "latency_ms": 115}
      ]
    }
  }
}
```

## 6. 测试与验证不变量 (Verification Invariants)

1. **离线高可用不变量**: 所有静态资源必须来源于本地 `/static/vendor/`，网络断开时不发生 CDN 404 崩溃。
2. **故障隔离不变量**: 当某个账户网络出现超时（例如代理波动）时，心跳记录标记该账户为失败/高延迟，但聚合池与其余账户配额抓取必须正常执行。
3. **输入焦点静音不变量**: 用户在搜索输入框或密码框键入 `1`、`2`、`r` 时，快捷键系统不得截断输入或触发误跳页。
