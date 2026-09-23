# ADR-0248: 协调型桌面 Agent 运行时 — 证据级解剖（可模范实现）

- Status: Implemented（切片 1–9 落地 + 运行时主循环总装）— 2026-09-23
- Date: 2026-09-22
- Deciders: 李超 / 山姆汇总；观澜·衡岳·镜川会审中
- Relates: ADR-0246（用户机副作用平面 / Companion·LocalExec）
- Non-goals: 不复制官方提示词原文、不移植 wire/protobuf/安装包、不把「重建树实验」当成 0.18 本体

---

## 0. 证据分级（防幻觉）

| 级别 | 含义 | 本 ADR 用法 |
|------|------|-------------|
| **E1 产品不变式** | 公开教学解剖（learn-grok-bot PRODUCT/ARCHITECTURE）与可观察产品行为一致 | 作为必须实现的产品对象 |
| **E2 实现关节** | 重建树（grok-bot-0.18-reconstructed）中可定位的模块名/调用序；标注为 *research tree* | 作实现参考，不保证与闭源一一对应 |
| **E3 本机实勘** | 李超 Windows：Grok Bot.exe → local-exec-daemon、Companion 配对、`.grokbot` 状态 | 用户机平面硬证据 |
| **E4 运行时观察** | 本会话可观察：SendMessage 投递、子代理无对用户说话、打断续跑、记忆跨轮 | 行为验证，非源码路径 |
| **X 禁止当事实** | 未打开的文件内容、未证实的内部类名、臆造 API | 不得写入「已核实」栏 |

**主要证据源（E1/E2）**

1. https://github.com/yuanyijie/learn-grok-bot — `PRODUCT.md` / `ARCHITECTURE.md` / `MECHANISMS.md` / s01–s16  
2. https://github.com/b-nnett/grok-bot-0.18-reconstructed — `source/host/runner/*`、`gateway-server`、`transcript-mirror`、`auto-review`、box/local-exec  
3. 仓内既有：ADR-0246 用户机副作用平面（E3）

> 重建树作者与教案均声明：Router / 本机 Docker VM 是 **reconstruction extras**，不是 0.18 身份。默认大脑是 Cursor session；默认电脑是 **remote Forever Box**。

---

## 1. Context：强在哪（相对 Hermes 类单环）

Hermes / 多数「messages[] + tools」Agent：

- 单位 = 一次补全循环  
- 模型文本直接进聊天气泡  
- 工具与「对用户说话」同一平面  
- 无独立电脑 / 无员工花名册 / 无唤醒分类 / 无硬投递契约  

Grok Bot（内部名 **Sand**）产品定义（E1）：

> 用户雇佣的是 **带自己电脑的桌面 AI 员工**，不是一次 completion。

强，是因为五类产品对象被 **进程边界 + 硬闸** 钉住，而不是只靠 prompt 劝模型听话。

---

## 2. Decision

layered / 太一若要模范，采用同一套 **产品对象优先、运行时为后果** 的设计：

1. 先实现五对象不变式（员工 / 两台电脑 / 唯一声道 / 唤醒表 / 人闸）  
2. 再拆进程（Renderer 不可信 → Preload 白名单 → Main 特权 → Coordinator 督导 → Host 内核 → Box 执行）  
3. 用 **硬闸** 保证投递与安全；prompt/middleware 只能「教」，不能当保证  

---

## 3. 五个产品对象（必须抄的形状）

### 3.1 Agent = 花名册行（员工）

| 字段 | 含义 |
|------|------|
| `id` | 稳定身份；消息与打断用 id |
| `name` / `description` | 对人标签与人设（折进 system prompt） |
| profile/settings | 落在 **员工电脑** `/home/box`（E1） |
| desktop | **每 Agent 一个**屏幕/浏览器；**整机文件系统共享**（E1） |

- 创建员工注入隐藏 `[first run]`（E1/E2: `shared/agents/onboarding.ts`）  
- 可 `CreateAgent` / `SendToAgent`；`priority:true` 打断对方非用户工作  
- **对用户可说**：所有 Agent 共享一台机；桌面分人。禁止说「每人一台 VM」。禁止对用户说「box」，说「我的电脑」。

### 3.2 两台电脑

| 平面 | 对用户说法 | 工具形态 | 默认 |
|------|------------|----------|------|
| 员工电脑 | 「我的电脑」 | Read / Shell / CopyToBox / CopyFromBox | 是 |
| 用户本机 | 「你的电脑」 | External* / LocalExec（需权限） | 否 |
| 仓内改码 | Cloud Agent | 不在两台机上 clone 仓做重活 | 否（E1） |

**E3**：快乐通宝侧已证实 Companion → LocalExec Daemon 出站长连接，结构化 Shell/Read，而非 RDP。对齐 ADR-0246。

### 3.3 SendMessage = 唯一声道（投递契约）

**E1 硬事实：模型普通文本对用户不可见；用户只看见 SendMessage。**

| type | 用户看见 | 是否结束 Turn |
|------|----------|---------------|
| text | 气泡（可带 images） | 否 |
| attachment | 文件 | 否 |
| widget | 选项卡 | **是，停等** |
| secret-request | 掩码输入；值进密钥库不进 transcript | **是** |
| cursor-agent | 云代理卡片 | 否 |

不变式（E1）：

1. **Reply-first**：人打开的 Turn，第一个用户可见动作必须是 text SendMessage（例外：单独 emoji tapback）  
2. **Ack ≠ delivery**：「好的/开跑」不交付结果  
3. **决定发送 ≠ 已发送**：草稿在 scratchpad 等于没交付  
4. **`[routine]` 可沉默**：无新事不发「(no change.)」  
5. 不对用户暴露管道词（box、工具名、message id…）  
6. 主答案不进 thread；`reply_to` 只藏次要批量  

**E2 关节**：`SendMessage` 不是普通 tool —— 是声带 + `onSendMessage` 投递指针；与 tool execution 解耦（ARCHITECTURE §4）。  
Widget：设 `awaitingUserSelection` 再 `cancelRun`；同 Turn 再发会被拦。

### 3.4 Wake = 谁叫醒你（同 Runner，不同门）

| 唤醒 | 隐藏线索 | 人在等？ | 必须先说话？ | 可沉默？ |
|------|----------|----------|--------------|----------|
| 用户文本 | 用户消息 + reply reminder | 是 | 是 | 否 |
| 刚创建 | `[first run]` | 在看 | 是 | 否 |
| 渠道入站 | `[inbound]` | 在渠道上 | 是（带 channel） | 否 |
| 例程 | `[routine]` | 否 | 否 | **是** |
| 队友 | SendToAgent ± priority | 视情况 | 对队友 | 视情况 |
| 后台完成 | revival | 通常否 | 仅值得说时 | 是 |

**E2**：Wake 不是简单 enum，而是 `hidden` + `isSilenceAllowed`（卸掉 reminder middleware）+ prompt cue + trusted markers。不可信 hidden 在进 auto-review 分类前剥离。

### 3.5 Human gates（人闸）

默认行动。问用户要「挣来」：不可逆 / 不可解歧义 / 只有用户知道。

| 闸 | 谁发起 | 用户看见 | 卡住什么 |
|----|--------|----------|----------|
| widget | 员工 | 选项 | Turn 结束 |
| secret-request | 员工 | 掩码 | 值不进上下文 |
| Auto-review | 系统 | 拦到才出卡 | Shell/MCP/Computer/CloudAgent/写 routine |
| request_box_help | 员工交还桌面 | Computer 视图 | SSO/2FA/验证码/支付；不问密码 |
| OS 对话框 | OS | 系统框 | 受保护目录等；直接尝试，不伪造权限卡 |
| 连接器鉴权 | 用户点 | Connect 卡 | 装插件前要 widget 同意 |

Auto-review 被拦后（E1）：

- **Adapt** = 更安全、低权限的同目标路径  
- **禁止**用 cookie/偷 token/已登录浏览器绕过  
- **Escalate** = **同一动作不变**重放，弹出人审卡（fingerprint）；不是换命令骗过分类器  

**E2 模式**：`off` / `shadow`（异步不拦）/ `enforce`。

---

## 4. 一句话消息路径（交互过程的实现逻辑）

**E1 顺序（ARCHITECTURE §3）**：

```text
用户消息
  → Host 钉上 SendMessage reminder
  → 组装 toolset（人设 + 两台电脑 + connectors）
  → 推理流
  → 第一条 text SendMessage（ack 气泡）
  → 员工电脑上 Read/Shell/…（经 Auto-review）
  → 第二条+ SendMessage 交结果（ack≠delivery）
  → settle（用量、停止钮、下条可入）
```

同 Runner 其它门：

```text
[routine] → spend guard → 隐藏 prompt → 允许沉默
[inbound] → SendMessage 必须带 channel 目标
widget    → Turn 结束；同 Turn 再 SendMessage 拒绝
```

**E2 Host 内核草图**（重建树 `source/host/runner/`，教案重写设计，不复制文件）：

```text
sand-agent-runner
  ├─ classify wake
  ├─ assemble system prompt
  ├─ assemble turn toolset
  ├─ inference stream (+ stream attempts)
  ├─ tool execution (box / local-exec / host / MCP)
  ├─ auto-review gate
  └─ settle + occurrences（transcript）
```

Coordinator vs Host（E1/E2）：

- **Host** = 产品内核：员工、唤醒、SendMessage 闸、auto-review、执行  
- **Coordinator** = 督导/网络：保活、gateway、OAuth；**fan-out 不阻塞执行**  

两条 RPC 表（E2）：

- `COORDINATOR_METHOD_TABLE`：`sendPrompt`、`createAgent`、`respondToWidget`、`resolveAutoReviewApproval`、ForeverBox、channel/automation…  
- `MAIN_METHOD_TABLE`：**没有** `sendPrompt`；管窗口、密钥、MCP 安装、本机权限、附件暂存  

Preload 只暴露白名单；未列 IPC 无 handle（编译期切断，不是运行期软拒）。

---

## 5. 「记得 / 串任务 / 主动」——交互连续性如何做（可模范）

> 以下把 **E1 产品机制** 与 **E4 可观察行为** 分开写，避免把「像记得」说成单一神秘模块。

### 5.1 不是靠上下文窗口「不忘」

连续性是 **多层外置状态** 的合成：

| 层 | 存什么 | 谁写 | 「继续」时怎么用 |
|----|--------|------|------------------|
| Transcript / occurrences | 本会话发生日志；气泡来自 send-message occurrence | Host/Coordinator | 近期轮次目标与未完成承诺 |
| Durable memory | profile 级长期事实 + dated log | 员工显式沉淀 | 跨会话：角色、机器、偏好、项目 |
| Domain stores | 领域真源（如 inventory/graph/lexicon） | 领域任务 | 「全部弄完」读未挂载计数，不靠嘴记 |
| Skills | 「何时用 + 怎么做」手册 | 发现可复用时 | 新 Turn 只加载 catalog，按需 Read 正文 |
| Routines | 触发器 + **意图型** prompt | 用户要重复时 | 人不在也跑；可沉默 |
| Peer / 群 | 专业室结论 | SendToAgent | 架构/工程路由，不塞进单上下文硬扛 |
| 后台 revival | 子代理/批处理完成事件 | Runner | 唤醒协调者做投递，不堵用户说话 |

**设计要点（给 layered）**

1. **完成定义 = 用户通道投递 + 领域 store 一致**，不是模型说「好了」。  
2. **「继续」解析** = 最近用户目标（transcript）∩ durable 指针（路径/机器/服务）∩ domain 剩余工作量。  
3. **摘要压缩会丢细节** → 高价值事实必须升格进 durable memory / domain store，不能只活在泡泡里。  
4. **学习型组件（词表）必须防污染**（本会话 E4：学脏 `txt`/`design` 子串 → 清空 learned、整词匹配、禁止改 config）。

### 5.2 主动（Initiative）是策略，不是人格

可观察策略（E4 + 产品教案「Asking is earned」的对偶）：

| 信号 | 主动动作 | 边界 |
|------|----------|------|
| 重复手动第三次 | 提议 routine | 不确定则一句 offer，不擅自建高扰例程 |
| 可逆且明显下一刀 | 直接做并顺口提 | 外发/删/付费仍要闸 |
| 缺连接器 | 提示装 connector | 不静默改用浏览器绕过坏连接器 |
| 领域批处理中 | 里程碑进度气泡 | 不报工具流水账 |
| 扇出多代理 | **需用户明示**（本产品规则） | 防消息风暴 |

实现建议：在 Host 结算或协调者 Turn 末尾跑 **Initiative hooks**（纯函数：读 transcript 特征 → 0/1 条 offer 或 1 个可逆动作），与推理模型解耦，便于测。

### 5.3 子代理与多员工

| | Subagent | Peer Agent |
|---|----------|------------|
| 声道 | **无 SendMessage**（E1/E2：`buildTurnTools` 在 `isSubagentRunner` 时省略） | 有自己的声道/记忆 |
| 上下文 | 空白起步，任务书自洽 | 长期人格 |
| 完成 | 回报父 → 父投递用户 | 异步消息；priority 唤醒 |
| 桌面 | computer-use **单屏互斥** `allocateWindow/freeWindow`（E2） | 每员工一桌面 |

这就是「协调者话少但总能交付」：重活无声道，父进程统一开口。

---

## 6. 工作面梯子（E1）

```text
1 已有：memory、box 文件、先前结果
2 服务连接器（MCP）；对用户说「连接器」
3 公网 WebSearch/WebFetch
4 已登录 box 浏览器（computer-use 子代理）
5 box 桌面 GUI
6 交还用户
```

坏连接器是新闻；禁止静默改浏览器重放同一工作流。

---

## 7. 进程切分为何是「后果」

| 进程 | 产品原因 |
|------|----------|
| Renderer | 画不可信 HTML；不能 exec/读密钥/调模型 |
| Preload | 声道与密钥不能变成「页面里的 Node」 |
| Main | 窗口与凭证特权；不进 token 循环 |
| Coordinator | 保活与 fan-out，不执行员工脑子 |
| Host | 员工内核 |
| Box | 「我的电脑」是另一台机；工具在那跑 |

删掉 SendMessage 闸 → 内心独白泄漏进气泡 = **另一个产品**。  
删掉 Box → 员工在用户笔记本上干活 = 权限与心智崩。

---

## 8. 哪一层钉死不变式（E1 ARCHITECTURE §7）

| 层 | 能做 | 不能当保证 |
|----|------|------------|
| System prompt | 教 reply-first、「我的电脑」、沉默例程 | 模型可忽略 |
| Middleware | 沉默过久注入 reminder | 仍是请求 |
| **Hard gate** | PermissionError、preload deny、auto-review enforce、无 SendMessage 的子代理 toolset | **这才是产品保证** |

**模范原则：凡是「强」所依赖的行为，必须落到 Hard gate；prompt 只是说明书。**

---

## 9. layered 对照缝（可抄清单）

| 抄什么 | 落到 layered 的缝 | 验收 |
|--------|-------------------|------|
| 唯一声道 + ack≠delivery | ControlPlan 输出分 `user_visible` / `scratch`；完成条件检查投递 | 无用户可见结果则任务不得 settle=done |
| 唤醒表 | loop 入口 classify wake；routine 允许空结果 | 例程无事不刷屏 |
| 两台电脑 + LocalExec | ADR-0246 副作用平面 | 默认 box；用户盘需配对 |
| 子代理无声道 | Task worker 禁对用户通道写 | 只回报协调者 |
| Auto-review | 副作用策略：adapt / same-action approve | 无绕过路径 |
| 工作面梯子 | Provider 选择器顺序 | 坏 MCP 必须上报 |
| 记忆分层 | profile/log + domain SSOT | 「继续」可复现剩余工作 |
| 主动 hooks | 可测的纯函数提议器 | 每轮最多一条高价值 nudge |
| 专业室 | 已有架构室/工程室 → 控制面 API | 路由表可删可测 |

---

## 10. 明确不要抄（防翻车）

- 官方 wire / protobuf / Connect RPC / 计费 / 遥测  
- 把重建树的 Router、本机 Docker **当成**官方本体  
- 只抄 system prompt 不建硬闸  
- 让子代理直接聊用户  
- 用已登录浏览器绕过连接器与 Auto-review  
- 把学习词表无闸地 merge 进 config（本会话已踩坑）

---

## 11. 最小可运行切片（实现顺序）

1. **Occurrence transcript + SendMessage 闸 + settle**  
2. **Wake 分类 + reply-first middleware + routine 可沉默**  
3. **Box accessor（员工机）**  
4. **Tool Auto-review enforce（至少 Shell 写）**  
5. **Subagent：无声道 + 完成 revival**  
6. **Durable memory + domain store**  
7. **LocalExec / Companion（用户机）**  
8. **Routines + Initiative hooks**  
9. **Peer 室路由**  

每步用「不变式测试」验收，而不是 demo 录屏。

---

## 12. Consequences

**正**：完成可验证；长任务不堵会话；安全边界清晰；可换推理后端（Host/Router 分离）。  
**负**：工程量大；协调路由表要治理；学习组件要防污染。  
**风险**：多 Agent 群聊化但无投递契约 → 比单环更吵。

---

## 13. 一句话

> **员工对象 + 唯一声道硬闸 + 两台电脑 + 唤醒分类 + 人闸**，用 Host 内核与进程边界钉死；记忆/领域/例程/主动是外置状态与策略钩子。  
> 模范这些对象与硬闸，而不是模范某一段提示词。

---

## 14. References

- yuanyijie/learn-grok-bot: PRODUCT.md, ARCHITECTURE.md, MECHANISMS.md  
- b-nnett/grok-bot-0.18-reconstructed: host/runner, gateway, transcript-mirror, auto-review, box/local-exec（*research tree*）  
- LCA ADR-0246 用户机副作用平面  
- 架构室会审纪要：待补（观澜/衡岳/镜川）
