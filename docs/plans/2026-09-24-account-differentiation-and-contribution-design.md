# 账号差异化权重、错峰接力流水线与贡献模型设计文档

> **Date:** 2026-09-24  
> **Status:** APPROVED  
> **Author:** Antigravity & User  
> **Autopilot Ladder:** DRAFT (AP-05)  
> **Scope:** `/home/lichao/agy-monitor-dashboard` (`app.py`, `static/index.html`, `test_dashboard_enhancements.py`)

---

## 1. 业务背景与问题定义 (Problem Statement)

在多账号集群控制台（0.0.0.0:1888）中，现有额度与任务看板存在如下认知与调度痛点：
1. **简单平均失真**：把 Google AI Pro 订阅账号（高配额、高阶模型、高并发）与 Starter 免费缓冲账号（低配额）按 1:1 简单算术平均，掩盖了集群真实等效算力储备。
2. **错峰相位未显性化**：每个账号重置周期（7天/168小时）的时间起点不同（如 B 账号 1.7 天后回血，C 账号 3.4 天后回血，E/F/I/J/K 在 5~7 天后回血）。这种“流水线接力、每天都有账号满血复活、永不枯竭”的核心调度优势未能直观呈现在大盘上。
3. **账号贡献不透明**：用户无法直观看出各账号为项目实际贡献了多少算力输出（Quota Burn 吞吐占比）以及交互工作量（Prompts 次数与总 Step 步数占比）。

---

## 2. 负向边界声明 (Does NOT own - AP-01)

- **Does NOT own**:
  - 严禁修改 `/home/lichao/layered-cognitive-agent/*` 认知协议、核心循环或底层代码。
  - 严禁修改各账号的 OAuth Token 凭证、Refresh Token 或登录态。
  - 严禁引入外部公共 CDN 链接（Tailwind/Vue/FontAwesome 均保留在 `/static/vendor/` 离线目录）。
  - 严禁修改非监控后台范围的系统服务。

---

## 3. 数学模型与算法设计 (Mathematical Models)

### 3.1 账号容量权重与等效加权配额池 (Capacity Weight)
定义每个账号的容量权重 $w_i$：
- **Google AI Pro 账号（A, B, C, E, F, I）**：$w_i = 3.0$
- **Starter 免费缓冲账号（J, K）**：$w_i = 1.0$

**加权等效算力池均值**：
$$Q_{weighted\_pool} = \frac{\sum_{i=1}^N (w_i \cdot Q_{actual, i})}{\sum_{i=1}^N w_i}$$

同时保留标准算术均值 $Q_{arith\_avg}$，便于对照。

### 3.2 7 天错峰回血流水线模型 (Rolling Pipeline Stages)
根据离完全重置时刻的剩余小时数 $T_{rem}$，将 8 账号划分为三大接力梯队并按重置时间升序排列：
1. **第一接力梯队（临近回血 / $T_{rem} < 48\text{h}$）**：
   - 策略标签：`⚡ 临近回血 (<48h)`
   - 调度策略：**优先榨干剩余算力 / 准备满血接棒**
2. **第二接力梯队（中坚过渡 / $48\text{h} \le T_{rem} \le 100\text{h}$）**：
   - 策略标签：`🛡️ 中坚接棒 (2-4天)`
   - 调度策略：**平稳承接核心攻坚**
3. **第三接力梯队（充沛储备 / $T_{rem} > 100\text{h}$）**：
   - 策略标签：`🔋 满血储备 (>4天)`
   - 调度策略：**高危时刻轮换底牌**

### 3.3 账号贡献模型 (Contribution Model)
1. **算力吞吐消耗贡献（Quota Burn Contribution）**：
   - 加权消耗量：$Burn_i = w_i \times \max(0, 100 - Q_{actual, i})$
   - 算力贡献百分比：
     $$\% \text{Burn Contribution}_i = \frac{Burn_i}{\sum_{k=1}^N Burn_k} \times 100\%$$
2. **交互工作量产出贡献（Workload Interaction Contribution）**：
   - 从 `history.jsonl` 与 `conversation_summaries.db` 读取交互 Prompt 次数 $P_i$：
     $$\% \text{Prompt Contribution}_i = \frac{P_i}{\sum_{k=1}^N P_k} \times 100\%$$

---

## 4. UI 呈现规范 (Visual Presentation)

1. **顶部全集群算力总览**：
   - 展示：加权等效算力池 %（对比算术均值）。
   - 新增：**「7天错峰回血接力流水线」横向微条**，8 节点按重置时间先后线性排列，呈现倒计时、余量微条与梯队标签。
2. **8 账号综合卡片**：
   - 等级与权重标签：`PRO (3×算力权)` / `FREE (1×缓冲权)`。
   - 回血倒计时与梯队角色徽章（如 `⚡ 周六 16:52 满血`）。
   - 集群贡献微标签：`🏆 算力贡献 38% · 交互 320 次 (35%)`。

---

## 5. 测试不变量 (Invariants to test - AP-02)

1. **INV-DIFF-01**: 加权配额池均值必然属于 $[0.0, 100.0]$。
2. **INV-DIFF-02**: 流水线排序必然按 `remaining_hours` 严格升序。
3. **INV-DIFF-03**: 当存在消耗时，各账号算力贡献百分比之和归一化为 $100.0\% \pm 0.2\%$。
4. **INV-DIFF-04**: Pro 账号的 `weight` 严格为 `3.0`，Free 账号的 `weight` 严格为 `1.0`。
