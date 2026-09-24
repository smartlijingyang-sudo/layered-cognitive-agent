# 7-Day Rolling Compute Forecast & Relay Schedule Design

## 1. Executive Summary & First Principles
用户在使用多账号算力集群（8 个活跃账号）时，除了获知“当前余量”，核心痛点在于**向前预测未来变化**：“明天会怎么变化？后天呢？接下来 7 天哪些号重置？算力如何恢复？怎么轮流接力？”

本设计在已有的“7天错峰接力流水线”基础上，构建前瞻性 **「未来 7 天算力回血预报日程表 (7-Day Rolling Forecast)」**。系统以真实 UTC+8 日历为基准，将接下来 7 天（Day 0 今天、Day 1 明天、Day 2 后天 ... Day 6）按天聚合成一张动态日程卡片流，直观呈现每天重置账号、恢复算力权单位、预计集群加权池跃升幅度，以及自动生成的日常运维与任务派发轮换建议。

---

## 2. 负向边界声明 (Does NOT own) 与治理等级

### 2.1 Owns (负责范围)
- `/home/lichao/agy-monitor-dashboard/app.py`:
  - 实现 `calculate_7day_forecast(quotas, accounts)` 算法。
  - 将 `forecast_7days` 注入 `calculate_cluster_aggregate` 及 `/api/cluster/live_tasks` 的返回体中。
- `/home/lichao/agy-monitor-dashboard/static/index.html`:
  - 在驾驶舱“7天错峰接力流水线”下方渲染横向 7 天日程卡片流组件（ForecastCalendarBar）。
  - 支持“明天/后天”动态高亮标签、满血倒计时芯片、恢复算力权徽章与每日调度接力建议。
- `/home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py`:
  - 增补 7 天预报算法单元测试与前端 DOM 不变量测试。

### 2.2 Does NOT own (禁止越界, AP-01)
- 严禁修改任何底层 LCA 认知契约、图算子、Session 状态机或数据目录。
- 严禁修改用户 OAuth Token 或任何真实凭据。
- 严禁引入任何外网 CDN 或未经本地化的资源，维持 100% 本地 vendor 离线保证。

### 2.3 Autopilot 等级 (AP-05)
- `DRAFT` 级别：修改限于 `agy-monitor-dashboard` 前后端，不改变底层架构与运行态。

---

## 3. 数学模型与算法推演

### 3.1 7 天连续日历窗口推演
设当前基准时间为 $T_{\text{now}}$（北京时间 UTC+8，例如 2026-09-25 周五）。
定义 7 天预测窗口为：
$$\mathcal{D} = \{ D_k \mid k \in [0, 6] \}, \quad D_k = \text{Date}(T_{\text{now}} + k \times 24\text{h})$$
- $k=0$: 今天 (周五)
- $k=1$: 明天 (周六)
- $k=2$: 后天 (周日)
- $k=3$: 大后天 (周一)
- $k=4$: 周二
- $k=5$: 周三
- $k=6$: 周四

### 3.2 账号重置点归组与算力权恢复测算
对每个账号 $i$：
- 提取其重置时间 $t_{\text{reset}, i}$（转换至 CST/UTC+8）。
- 计算剩余时间 $T_{\text{rem}, i} = (t_{\text{reset}, i} - T_{\text{now}})/3600$。
- 若 $0 \le T_{\text{rem}, i} \le 168$，则该账号在日期 $D_{\text{target}}$ 满血重置，归入对应天数桶 $Bucket(D_{\text{target}})$。

对于每一天 $D_k$：
- **当天重置账号数**：$N_k = |Bucket(D_k)|$
- **恢复算力权单位（Capacity Units Restored）**：
  $$W_{\text{restored}, k} = \sum_{i \in Bucket(D_k)} w_i$$
  （其中 Pro 账号 $w_i = 3.0$，Free 账号 $w_i = 1.0$）
- **预计全集群加权算力池跃升量（Pool Lift Pct）**：
  $$\Delta Q_{\text{pool}, k} = \frac{\sum_{i \in Bucket(D_k)} w_i \times (100 - Q_{\text{actual}, i})}{W_{\text{total}}} \times 100\%$$
- **智能接力策略建议（Relay Recommendation）**：
  - 若 $N_k > 0$：列出最先回血的账号及精准时间（如“⚡ 账号 B 于 16:52 满血，恢复 3× 算力权，建议届时主力切入 B 攻坚”）。
  - 若 $N_k = 0$：提示中坚支撑（如“🛡️ 纯消耗蓄能期，由前期满血的 A/B 账号扛压，避免单号超频”）。

---

## 4. 测试断言与架构不变量 (AP-02)

1. **时间连续性不变量**：`forecast_7days` 长度严格等于 7，日期严格从今天递增至第 7 天，无断裂。
2. **账号覆盖守恒不变量**：全集群 8 个账号的所有周度重置点在 7 天预测窗口内严格且恰好出现一次，$\sum_{k=0}^{6} N_k = 8$。
3. **恢复算力权守恒不变量**：7 天内累计恢复的总算力权严格等于全集群总容量单位：
   $$\sum_{k=0}^{6} W_{\text{restored}, k} = 6 \times 3.0 + 2 \times 1.0 = \mathbf{20.0}$$
4. **前端不变量**：HTML 中必须包含 `forecast_7days`、`7天回血预报`、`恢复算力`、`接力建议` 对应标签与离线样式。
