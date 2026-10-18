# 决策大脑与场景执行彻底解耦：工业级拟真自动化四层架构设计文档

**文档编号**：`PLAN-20261018-STOCHASTIC-DECOUPLE-DESIGN`  
**编制时间**：2026-10-18  
**设计目标**：彻底消除 Playwright 自动化中的硬编码面条逻辑与均匀伪随机特征，借鉴游戏 AI（NPC Utility AI + Blackboard）与微内核架构，构建“控制面（马尔可夫+效用大脑）与执行面（Playwright 原子场景插件）完全解耦”的四层架构，配备零 DOM 污染的双屏实时监控大盘与确定性回放调试能力。  
**架构状态**：`APPROVED` (经过 3 轮结构化设计呈批，用户审核确认采纳方案 A)

---

## 一、 架构背景与面条脚本痛点根因分析

在传统自动化与脚本编写中，开发者通常习惯于将控制流直接写死在执行代码中：
```python
# 典型面条脚本反模式 (Anti-Pattern)
while True:
    action = random.choice(["feed", "search", "unfollow", "notify"])
    if action == "feed":
        page.goto("https://x.com/home")
        time.sleep(random.uniform(2, 5))
        # 夹杂 DOM 操作、滚动、点赞...
```
这种代码在工业级场景下存在两大致命缺陷：
1. **代码迅速退化为不可维护的面条代码**：
   * 原有 `x_operator/scheduler/scenarios.py` 膨胀至 78KB，业务逻辑、DOM 操作、随机 sleep、异常重试全部揉杂在一起，无法单独编写单元测试，修改一个场景极易引发其它场景的回归缺陷。
2. **时序与行为特征在统计学上呈现机械感**：
   * 各场景 25% 均等概率跳转属于典型的**均匀伪随机（Uniform Pseudo-Random）**。真实人类使用社交软件具有极高的**高偏度（Skewness）**与**重尾特征（Heavy-Tailed Distribution）**——真人 65%~70% 的时间在刷主页，写操作（发推、评论、取关）属于低频偶发行为。
   * 现代反作弊时序分析模型（Behavioral Timing & Navigation Sequencing）会精准检测转移序列的马尔可夫阶数与熵值，死板的脚本极易被判定为 Bot 并遭隐形降权或风控封禁。

---

## 二、 架构范围与治理边界（Owns / Does NOT own）

### 1. 明确 Owns（本次架构升级必须建设的内容）
1. **全量切除旧版面条与静态轮盘**：
   * 废除 `x_operator/scheduler/roulette.py`（旧版静态权重轮盘）与 `x_operator/scheduler/scenarios.py`（78KB 的面条脚本）。
2. **落地顶级四层纯解耦架构体系**：
   * **层 1：生理节律层（Macro Clock）**：落地 `CircadianFatigueEngine`，通过非齐次泊松过程（Inhomogeneous Poisson Process）计算真实上线唤醒时机，结合指数疲劳衰减积分模型计算当前精力值。
   * **层 2：决策调度层（Control Plane）**：落地 `StochasticDecisionBrain`，实现二阶马尔可夫转移矩阵、动态效用因子修饰器（Utility Modifiers）、对数正态时长采样与 8% 分心中断引擎。**绝不触碰任何 Playwright/DOM/浏览器对象**。
   * **层 3：场景编排层（Tactical Plugins）**：落地 `SceneSkillRegistry` 微内核插件注册中心，将 5 大核心场景抽离为高内聚、单文件插件（`ForYouScene`、`SearchInteractScene`、`NotifyScene`、`GraphFollowScene`、`RestIdleScene`），统一实现 `SceneSkill` 契约协议（`can_run()`, `execute()`, `interrupt()`）。
   * **层 4：物理执行层（Execution Plane）**：封装纯净的 `StealthActuator` 端口，强制提供 `NavigationRouter`（100% SPA 原生点击路由，严禁 `page.goto`）、`BiometricMotor`（WindMouse 动力学 + 2D 高斯落点）、`KeystrokeEngine`（拟真错字退格纠错）与 CDP 旁路监听器。
3. **状态黑板与异步事件总线（Blackboard & Event Bus）**：
   * 建立强类型 `SessionBlackboard`（Pydantic V2 frozen snapshot），维护生理状态、红点数、读写比（14:1）、配额与冷却锁；物理层通过 `RiskSignalEvent`、`BadgeStimulusEvent` 等异步事件触发大脑毫秒级自愈。
4. **Web 实时双屏可视化大盘服务（Dual-Screen Telemetry）**：
   * 在 FastAPI 后端提供 WebSocket 推流服务，广播决策大脑转移帧与执行层 HUD 帧（透明 SVG 贝塞尔曲线、高斯热力点），挂载于 Web 控制台。

### 2. 严格声明 Does NOT own（坚决不触碰的负向边界，AP-01）
1. **不修改底层浏览器指纹与反反爬驱动核心**：
   * 不修改 Camoufox 底层 C++ 二进制或 Chromium 的 patch 规则；仅通过公开 API 调度原子拟真操作，严禁侵入浏览器二进制/内核层。
2. **不改变数据库核心业务表 Schema**：
   * 沿用现有的 `comments`、`posts`、`traces` 物理分库表结构，不引入破坏性数据库迁移。
3. **不触碰 LCA 框架内核与宿主机非相关资产**：
   * 本项工作专属自治于 `/home/lichao/tools/x-operator` 项目内部，严禁将特定业务代码提交至 LCA 核心仓库。

### 3. 爆炸半径自治等级（Autopilot Ladder，AP-05）
* **评定等级**：**`DRAFT`（核心业务控制面全量重构，必须通过逐步设计呈批与全套自动化测试套件守卫）**

---

## 三、 顶级四层解耦架构模型

```text
+-----------------------------------------------------------------------------------+
|                        1. 生理节律层 (Circadian & Fatigue Engine)                   |
|  • 非齐次泊松过程唤醒器 (Inhomogeneous Poisson Process)                            |
|  • 指数疲劳累积与衰减模型 F(t) = F0 + ∑ ΔFk * exp(-α(t - tk))                     |
+-----------------------------------------------------------------------------------+
                                          │ 注入宏观状态向量
                                          ▼
+-----------------------------------------------------------------------------------+
|                     [共享状态黑板 SessionBlackboard & 事件总线]                     |
|  [疲劳度 F | 昼夜时相 | 通知红点数 | 取关冷却锁 | 今日配额 | 读写比 14:1 | 风控熔断信号]  |
+-----------------------------------------------------------------------------------+
                                          │ 实时环境感知输入
                                          ▼
+-----------------------------------------------------------------------------------+
|                        2. 决策调度层 (Stochastic Decision Brain)                    |
|  • 二阶马尔可夫基准矩阵 P_base(St -> St+1)                                        |
|  • 动态效用修饰器矩阵 U(Sj | Blackboard)                                          |
|  • 对数正态时长预算采样 T ~ LogNormal(μ=4.2, σ=0.45)                               |
|  • 8% 注意力半途分心中断 (Attention Span Drop)                                     |
|  * 绝对纯净：0 行 Playwright/DOM/网页依赖，纯数学与状态推演                           |
+-----------------------------------------------------------------------------------+
                                          │ 下发目标 Scene ID + 时长预算 + 中断标记
                                          ▼
+-----------------------------------------------------------------------------------+
|                        3. 场景编排层 (Tactical Scene Plugins)                      |
|  • 微内核插件注册中心 (SceneSkillRegistry)                                          |
|  • 单文件独立场景插件 (实现 can_run(), execute(), interrupt()):                     |
|    - ForYouScene (推荐流惯性滚动与神评互动)                                        |
|    - SearchInteractScene (搜索定向关键词、看详情、口语发评)                         |
|    - NotifyScene (通知流回关回赞、消除红点角标)                                    |
|    - GraphFollowScene (低频关系维护、触发 4-8h 冷却锁)                              |
|    - RestIdleScene (放空、切后台、挂起等待、精力回血)                               |
+-----------------------------------------------------------------------------------+
                                          │ 仅调用原子拟真指令
                                          ▼
+-----------------------------------------------------------------------------------+
|                        4. 物理执行层 (Stealth Actuator)                           |
|  • NavigationRouter: 100% SPA 原生点击路由 (拦截 page.goto)                        |
|  • BiometricMotor: WindMouse 贝塞尔动力学寻路 + 截断 2D 高斯落点                   |
|  • KeystrokeEngine: 键盘拟真敲击 + 伴随错字退格纠错                                 |
|  • CDP 旁路监听: 监控 GraphQL 响应，捕获 429 瞬间抛出 RiskSignalEvent 反哺黑板     |
+-----------------------------------------------------------------------------------+
```

---

## 四、 马尔可夫效用决策大脑核心数学模型

### 1. 基础转移矩阵（Base Transition Matrix $P_{\text{base}}$）
定义系统在处于场景 $S_t$ 时，下一步跳转至 $S_{t+1}$ 的基准概率：

| 当前场景 $S_t$ | $\to S_1$ (For You) | $\to S_2$ (Search) | $\to S_3$ (Notify) | $\to S_4$ (Graph) | $\to S_5$ (Rest) |
|---|---|---|---|---|---|
| **$S_1$: For You 推荐流** | **0.50** | 0.18 | 0.15 | 0.02 | 0.15 |
| **$S_2$: 搜索互关评论** | **0.65** | 0.10 | 0.15 | 0.02 | 0.08 |
| **$S_3$: 清理 Notification**| **0.60** | 0.25 | **0.00** | 0.05 | 0.10 |
| **$S_4$: 低频关系管理** | **0.70** | 0.10 | 0.10 | **0.00** | 0.10 |
| **$S_5$: 发呆/休眠** | **0.85** | 0.05 | 0.10 | 0.00 | **0.00** |

*注：$S_3 \to S_3$ 和 $S_4 \to S_4$ 转移概率恒为 0，严禁连续清理通知或连续取关。*

### 2. 动态效用修饰器（Utility Modifiers $U(S_j \mid \mathbf{e})$）
在每次决策前，从黑板提取特征，动态计算各候选场景的效用乘数：
1. **红点视觉强迫症 (Badge Stimulus)**：
   $$U(S_3) = \begin{cases} 3.5 \times (1 + 0.2 \cdot \min(\text{badge}, 5)), & \text{if badge} > 0 \\ 1.0, & \text{otherwise} \end{cases}$$
2. **高风控冷却锁 (Cooldown Gate)**：
   $$U(S_4) = 0.0 \quad (\text{若取关冷却锁激活})$$
3. **每日配额衰减 (Comment Quota Gate)**：
   $$U(S_2) = \begin{cases} \exp\left(-1.5 \cdot \frac{N_{\text{used}}}{N_{\text{max}}}\right), & \text{if } N_{\text{used}} < N_{\text{max}} \\ 0.0, & \text{if } N_{\text{used}} \ge N_{\text{max}} \end{cases}$$
4. **生理疲劳抑制 (Fatigue Suppression)**：
   $$U(S_5) = \exp(2.8 \cdot F), \quad U(S_2) = \max(0.05, 1 - 0.9F), \quad U(S_4) = \max(0.05, 1 - 0.9F)$$
5. **风控紧急避险 (Risk Hazard Gate)**：
   若监听到 HTTP 429 或 Arkose 验证码：
   $$U(S_2) = 0.0, \quad U(S_4) = 0.0, \quad U(S_5) = 15.0$$
6. **归一化概率分布**：
   $$W(S_j) = P_{\text{base}}(S_t \to S_j) \times U(S_j \mid \mathbf{e})$$
   $$P_{\text{final}}(S_t \to S_j) = \frac{W(S_j)}{\sum_{k=1}^5 W(S_k)}$$

---

## 五、 Playwright 场景切换三大工程铁律落地规范

1. **铁律 1：严禁使用 `page.goto()` 进行场景跳转**：
   * 必须封装 `NavigationRouter`。通过拟真鼠标点击左侧导航栏图标（`a[data-testid="AppTabBar_Notifications_Link"]` 等）或调用浏览器原生后退键触发单页路由流转，保持前端 React 内存中 `client_event.json` 遥测埋点队列与 WebSocket 链路的连续性。
2. **铁律 2：场景插件内部为微状态机（Micro-State Machine）**：
   * 每个场景插件内部按微状态流转，如 `SearchInteractScene` 内部细分为：
     $$\text{定位搜索框} \to \text{输入关键词} \to \text{浏览 3-5 条推文} \to \text{点进详情页} \to \text{口语发评} \to \text{退出}$$
   * 严禁在脚本中编写任意无状态的 `time.sleep`，所有停顿由阅读注意力阻尼模型计算。
3. **铁律 3：异常感知与 GraphQL 旁路自愈**：
   * 底层通过 `page.on("response")` 旁路监听所有请求。一旦捕获 HTTP 429 或安全挑战标记，执行层不进行自作主张的死循环重试，而是立即向总线抛出 `RiskSignalEvent`，决策大脑毫秒级切入休眠避险。

---

## 六、 零 DOM 污染透明 HUD 监控大盘架构

* **杜绝 DOM 污染**：严禁在受控目标页面的 DOM 树中注入任何调试 `<canvas>` 或辅助视觉元素，规避反作弊脚本的 `MutationObserver` 探测。
* **双平面分层渲染**：
  1. **底图层**：通过 CDP 旁路推流 `Page.startScreencast` 将真实浏览器画面投射在 Web 右屏。
  2. **透明 HUD 覆盖层**：在监控网页端，直接在视频顶层叠加同分辨率的透明 SVG/Canvas 视口。
  3. **实时轨迹映射**：`BiometricMotor` 在计算贝塞尔控制点时，将轨迹流通过 WebSocket 发送给前端，在透明 SVG 视口上实时画出绿色贝塞尔虚线预测轨迹、高斯热力圈与阅读倒计时。

---

## 七、 自动化测试不变量断言矩阵（Invariants in Tests，AP-02）

所有架构与行为不变量均由自动化单测和端到端测试守护：

| 不变量编号 | 核心断言内容 | 覆盖测试方法 |
|---|---|---|
| **INV-DECIDE-01** | 任何黑板状态下，动态效用修正后所有候选场景概率和恒等于 $1.0 \pm 10^{-6}$，且非负 | 参数化测试随机生成 100 种黑板环境组合并断言 sum(probs) == 1.0 |
| **INV-DECIDE-02** | 当 `badge_count > 0` 时，`NOTIFY` 场景效用乘数严格 $\ge 3.5\times$ | 单测注入红点信号，断言效用因子与归一化概率显著跃升 |
| **INV-DECIDE-03** | 取关冷却锁激活时，关系管理场景转移概率恒等于 `0.0` | 单测激活冷却锁，蒙特卡洛抽样 2,000 次断言命中次数为 0 |
| **INV-DECIDE-04** | 疲劳度 $F \ge 0.85$ 时，写操作总概率 $\le 0.08$，休息概率 $\ge 0.40$ | 单测注入极端疲劳，断言写操作被彻底压制与休息概率剧增 |
| **INV-ACT-01** | 全场景流转中除初始启动外，严禁发生任何 `page.goto` 调用 | Monkeypatch 拦截 `Page.goto`，一旦触发直接 Fail-Loud |
| **INV-ACT-02** | 鼠标轨迹加速度连续且无瞬移，点击落点在目标元素内呈截断 2D 高斯分布 | 采集 50 次点击坐标，验证高斯方差与边界合法性 |
| **INV-RISK-01** | 拦截到 429 响应后，事件总线在 50ms 内通知大脑将写操作清零并切入休眠 | 模拟 CDP 注入 429，断言黑板状态与下一决策帧写操作权重归零 |
