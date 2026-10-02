# ADR-0268 — 上下文总线、四类异步执行体与 cron 即将到来投影

## 状态

**Proposed — 2026-10-02**

> **一句话**：模型只有一条总线，就是上下文里的文本。四类异步执行体都是发出后由 runtime 回注，模型不轮询。定时任务是其中独立的一种。右侧「即将到来」读服务端算好的下次触发，不在浏览器里推算。

**Extends**：

- [ADR-0255](0255-muse-production-runtime-full-reference.md) 是 Muse 工具与 cron 的参考清单。本 ADR 决定 LCA 采纳其中哪一段、以什么名字落地。
- [ADR-0256](0256-tool-namespace-taxonomy.md) 的 8 域继续有效。本 ADR 只增加 `lca` 与 `cron` 两个域，不把 `file` / `shell` / `memory` 改名。
- [ADR-0257](0257-delegation-context-inheritance-and-verification.md) 继续管团队委派信封。本 ADR 的 cron worker 与 subagent 都不是那条信封。
- [ADR-0263](0263-routine-scheduling-mutual-exclusion-and-self-healing.md) 的锁、stale 收割、失败隔离继续有效。本 ADR 只修订 C1 里「忙则 SKIP、不排队」对 `CronJob` 的适用，见 §8。0263 文件不改。
- [ADR-0264](0264-proactive-messaging-pipeline.md) 继续管预先写好的主动消息。它的 `SILENT` 是裁决函数的返回值。本 ADR 的静默是 handoff 轮上的工具调用，两者不合并。

**不 supersede**：ADR-0047 的工具回注、ADR-0093 的工作队列、ADR-0187 的助理任务字符串、ADR-0248 的例程预算闸。它们保持原职责。本 ADR 不把它们变成 cron。

---

## 0. 接任务前 7 问

1. **问题是什么？** 用户要在对话右侧看到每周、每天、每小时的任务，能读下次触发时间，能改。用户在对话里提到提醒时，助理要能建任务。到点要有人干活。干完的例行结果默认不打断用户。用户没看到气泡时，仍能确认任务跑过。
2. **受影响的事实或契约是什么？** 任务定义、下次触发时间、worker 能看见的上下文、handoff 文本、静默信号、投递目标、右侧列表的数据来源。
3. **唯一真值在哪里？** 任务定义在 `CronJob` 存储。下次触发时间是 `next_run` 对这份定义的纯函数，不是前端状态，也不是模型上下文。某次运行的结果是追加的 run 记录。卡片是这两份事实的投影。
4. **改变哪个边界？** 工具命名空间增加 `lca` 与 `cron`。调度与执行与投递分成三个所有者。右侧栏增加一个只读投影加用户编辑入口。0263 的「不排队」对 `CronJob` 改为「运行中的留下，排队只留最新一次」。
5. **现有 Protocol / ADR 能否表达？** 不能。0255 是参考，不是 LCA 契约。0264 在工人报告出来之前就决定说不说。`RoutineSpec` 允许 cron 表达式和间隔同时存在或同时为空，调度器不读这两个字段。`JobSpec.schedule` 是不解析的字符串，HTTP 固定 501。三套记录都没有对客户端暴露的 `next_run`。
6. **失败、重试、恢复和幂等语义是什么？** 见 §7、§8、§9。runtime 失败和超时可按 `max_retries` 重试。worker 自己报告没做完，不重试。同一 id 的 `cron.add` 不覆盖。删任务和改周期要等审批回注。
7. **如何验证？** §14。

---

## 1. 上下文是唯一总线

模型没有供 runtime 写入的内存变量。用户消息、工具结果、handoff、记忆摘录、文件内容，都变成注入上下文的文本。模型的下一步只根据这些文本决定。

落盘文件是总线之外唯一扛过压缩的状态。`CronJob` 文件、`MEMORY.md`、run 记录在压缩后仍在。没写入这些存储的内容，压缩后不可恢复。

因此：

- 下次触发时间写在读取投影里，不写在对话里。
- worker 报告先落入 run 记录，再作为文本注入父轮。注入失败可以重放，不依赖父对话还留着原文。
- 记忆的写入是对 `MEMORY.md` 的文件编辑。本 ADR 不新增 `memory_write`。读记忆仍走 ADR-0256 的 `memory` 域与 ADR-0260 的写盘回执。

---

## 2. 工具调用是请求，然后回注

模型发出一次工具调用后，本轮停在这次调用上。runtime 执行，把结果作为新的工具消息注入，模型看到结果再决定下一步。模型不在同一次补全里假定执行已经完成。

这条规则覆盖同步工具，也覆盖 §3 的四类异步执行体。异步执行体的差别只有两处。谁触发。执行体是什么。回注的形态都是一条后到的消息。模型不轮询。

审批卡片是同步阻塞的一种回注。runtime 挂起这次调用，用户点选之后，点选结果作为工具结果注入。未点选之前，这次调用没有结果。删数据和改周期走这条路径，见 §9。

---

## 3. 四类异步执行体

四类都遵守 §2。上下文种子、失败和隔离各不相同。禁止用其中一类的实现去充当另一类。

| 执行体 | 触发 | 执行的东西 | 出生时看见什么 | 完成时回注什么 |
|---|---|---|---|---|
| exec 后台 | `background: true`，或超过 `yield_ms`（默认 10000 毫秒） | 该 agent 作用域内的一个 OS 进程 | 无模型上下文 | 退出码和完整 stdout/stderr |
| subagent | `subagent.spawn` | 独立 turn loop 的 agent | 出生时刻父上下文的冻结副本 | 该 agent 的最终回复 |
| browser task | `browser.spawn_task` | 浏览器操作 agent 加一台持久 Chromium | 任务书。不含父聊天记录 | 完成、卡住或待审批的 handoff |
| cron worker | 调度器到点 | 独立 turn loop 的 agent | 任务 `body` 加产品上下文。不含父聊天记录 | 见 §6。`space_action` 成功时不回注 |

### 3.1 exec 后台

立刻返回 `session_id`。stdout/stderr 由 runtime 缓冲。`process.log` 读这份缓冲。`process.write` 写 stdin。`process.send_keys` 只在 PTY 模式发送终端按键。`process.poll` 在 timeout 内等待新输出。`process.kill` 杀掉该会话的进程树。`process.clear` 丢弃已结束会话的缓冲。

会话按 agent 隔离。子 agent 看不见父的后台进程，父也看不见子的。VM 重启或替换后，这些进程不恢复。

远端机器上用 `setsid`、`nohup` 挂起的进程不属于本执行体。ssh 会话断开后的存活问题由那条远端命令自己处理。

定时任务禁止用常驻 exec 充当。时钟在 cron 服务里，不在一个 shell 循环里。

本 ADR 规定上述契约。验收 §14 不要求本轮实现 exec 后台。现有 `shell` 域工具保持 ADR-0256 的职责。

### 3.2 subagent

`subagent.spawn` 立刻返回 agent id。runtime 复制父在出生时刻的完整上下文。之后父的新消息、新工具结果不进入子。子跑自己的 turn loop。

子的工具集与父相同，除三类禁令。不得启动 browser task。不得构建 artifact。`max_depth` 为 2。父是 0，子是 1，孙是 2。深度 2 再 spawn 被拒绝。

子的 exec 后台会话和记忆写入在子自己的作用域。子结束（完成、失败、`close`）时，runtime 把最终回复作为 handoff 注入父。

`subagent.send` 只表示已入队。子当前 turn 结束后才看得到。`interrupt: true` 先打断当前 turn，再投递。`subagent.list` 的状态闭集是 `running`、`done`、`interrupted`、`failed`。`running` 带已运行时长和上次活跃时间。

这条执行体不替代 ADR-0257。团队成员、peer、接力委派仍用 0257 的信封（standing 全量、父 turn 摘要、记忆投影），不复制完整父 transcript。`subagent.spawn` 若将来实现，是另一个入口，不改 `MemberInvoker`。

本 ADR 规定上述契约。验收 §14 不要求本轮实现 `subagent.spawn`。

### 3.3 browser task

`browser.spawn_task` 接收一份自包含任务书，里面有目标站点、要做的事、成功标准。它不是通用子 agent。执行体是浏览器操作 agent，加上该用户 VM 里的一台真实 Chromium。profile 持久。cookie、登录态、tab 跨 task 保留。

决策循环是看截图和页面结构，再点击或填写，再看。遇到 CAPTCHA、登录墙或支付确认时暂停，handoff 给父。父用 `browser.steer_task` 继续。`browser_task_id` 与 subagent id 是两套标识。用错 id 拒绝。

支付、发消息和删除走审批卡片。用户可以观看并接管该浏览器窗口。

`browser.search` / `browser.open` 只读页面文本，不能点击、填写、登录。需要动手的操作必须走 `spawn_task`。

本 ADR 规定上述契约。验收 §14 不要求本轮实现 browser task。

### 3.4 cron worker

调度器到点，用任务的 `body` 原文启动 worker。worker 与父隔离。它看不见父的聊天记录、工具结果和 birth 之后的新上下文。

worker 的初始上下文只有：

- `body` 原文
- 产品上下文。`job_id`、`owner`、workspace 路径、timezone、`report`、`delivery_targets`、本次 `run_id`

`execution.kind = agent` 时，worker 跑完交出 `worker_message`。runtime 把它包成 §6 的 handoff，注入父的下一轮。父按 §6 决定说不说。

`execution.kind = space_action` 时，worker 只更新指定 artifact。成功不产生 handoff，不产生聊天气泡。runtime 失败或超时在重试耗尽后仍产生 handoff，否则刷新失败对父不可见。

---

## 4. 两个新命名空间

`lca` 是运行时控制，不是第二套文件或 shell 工具，也不是 `smart`。

| 工具 | 何时在 wire 上 | 参数 | 效果 |
|---|---|---|---|
| `lca.nothing_to_do` | 仅当本轮输入是 §6 的 handoff，且本轮没有更新的用户消息 | 无 | runtime 结束本轮，不写 assistant 可见气泡 |

用户消息触发的轮次上，这个工具不在 wire 上。模型若仍发出该调用，runtime 回注错误，本轮继续，不得把它当成静默。模型什么都不写，也不是静默。runtime 仍等待可见回复或这个工具。

`cron` 是调度服务，DEFERRED，经 `tool_search` 加载。VM 里没有 crontab。

| 工具 | 效果 |
|---|---|
| `cron.add` | 新建。id 已存在则返回现有记录，不修改 |
| `cron.view` | 按 id 返回全量定义 |
| `cron.update` | 以 `cron.view` 的全量记录覆盖。调用方先读再写 |
| `cron.remove` | 删除定义与尚未注入的 handoff。走 §9 审批 |
| `cron.list` | 返回该 owner 的投影，含 `next_run_local` |

`file`、`shell`、`memory`、`skill` 的现有工具不改名，不在 `lca` 下再注册一份。

---

## 5. CronJob

一份定义，一种 schedule。禁止「cron 表达式和间隔可以同时有，也可以同时没有」。

```python
class IntervalSchedule(BaseModel):
    kind: Literal["interval"]
    every_seconds: int  # > 0

class HourlySchedule(BaseModel):
    kind: Literal["hourly"]
    minute: int  # 0–59。每小时的这一分钟

class DailySchedule(BaseModel):
    kind: Literal["daily"]
    hour: int    # 0–23
    minute: int  # 0–59

class WeeklySchedule(BaseModel):
    kind: Literal["weekly"]
    weekday: int  # 0 = 周一 … 6 = 周日
    hour: int
    minute: int

class AgentExecution(BaseModel):
    kind: Literal["agent"]

class SpaceActionExecution(BaseModel):
    kind: Literal["space_action"]
    artifact_id: str

class ChatDelivery(BaseModel):
    chat_id: str

class CronJob(BaseModel):
    id: str
    title: str
    schedule: IntervalSchedule | HourlySchedule | DailySchedule | WeeklySchedule
    timezone: str  # IANA。缺省 Asia/Shanghai。ZoneInfo 不能加载则拒绝
    body: str
    execution: AgentExecution | SpaceActionExecution
    delivery_targets: tuple[ChatDelivery, ...]
    report: Literal["always", "anomalies_only"]  # 缺省 anomalies_only
    owner: str
    created_chat_id: str
    enabled: bool
    max_retries: int  # >= 0。缺省 0
    timeout_seconds: int | None  # None 表示按 §7 推导
```

约束：

- `agent` 的 `delivery_targets` 至少一条。`space_action` 的 `delivery_targets` 必须为空。
- `created_chat_id` 是侧聊时，每条 `delivery_targets.chat_id` 必须等于 `created_chat_id`。否则 `cron.add` 和 `cron.update` 拒绝。侧聊任务不能投到主聊天，也不能在主聊天里创建。
- `owner` 被删除时，其下 `CronJob`、run 记录和未注入 handoff 一并删除。
- `report` 写进 worker 的产品上下文和 handoff 的 `task_context`。runtime 不根据 `report` 丢弃 handoff。说不说由父在看到 `worker_message` 之后决定。

`next_run` 是纯函数。它不读时钟。调用方传入 aware 的 `now`。naive datetime 拒绝。

- 小时、日、周。返回该 timezone 下严格晚于 `now` 的下一次墙钟。`now` 正好卡在触发点上时，取再下一档。
- 间隔。`last_run` 为空时，结果等于 `now`（首次到期）。`last_run` 有值时，从 `last_run + every_seconds` 起按间隔前进，直到大于等于 `now`。
- 返回值是该 timezone 的 aware datetime。投影字段 `next_run_local` 格式为 `YYYY-MM-DD HH:MM`。

`enabled = false` 时仍计算 `next_run_local`，并在投影里标出停用。停用任务不到点。

存储只有一个写入者。路径是助理 home 下的 `cron/<job_id>.json`。定义用原子替换写入。run 记录追加在 `cron/<job_id>/runs/`。`ProactiveJob`、`RoutineSpec`、`JobSpec` 都不是这份存储。

`RoutineSpec.cron_expr` 与 `interval_seconds` 在实现本 ADR 时删除，不留双字段兼容。例程若仍需要 ADR-0248 的预算闸，引用 `CronJob.id`，不自带第二套钟。`GET/POST /v1/assistants/{id}/jobs` 在接到 `CronJob` 存储之前保持 501。接到之后，该路由读写 `CronJob`，不再接受未解析的 schedule 字符串。

---

## 6. Handoff 与说不说

`agent` 执行，以及 `space_action` 在重试耗尽后的 runtime 失败，产生一条 handoff。成功的 `space_action` 不产生。

```python
class ScheduledHandoff(BaseModel):
    job_id: str
    run_id: str
    task_context: CronJob  # 触发当时的定义副本
    worker_message: str
    delivery_targets: tuple[ChatDelivery, ...]
    outcome: Literal["completed", "runtime_failure", "timed_out"]
```

runtime 把这条记录作为 developer 消息注入父的下一轮。父不订阅、不轮询。注入前记录落在 run 日志里。父对话被压缩不影响重放。

父的决定：

| 条件 | 父必须做的 |
|---|---|
| `report = always`，或用户在 `body` / 当时对话里明确要求每次都收到 | 在回复里写出报告 |
| `worker_message` 里有新的失败、变化或需要人处理的事 | 写出报告 |
| 例行无异常，且 `report = anomalies_only` | 调用 `lca.nothing_to_do` |

写出报告时，正文进入 `delivery_targets` 里的 chat。多个目标各写一份。目标 chat 不存在则该目标失败，其他目标仍写，run 记录记下每个目标的结果。

`lca.nothing_to_do` 成功后，run 记录的 `delivery` 为 `silent`。卡片用这个字段表示「跑过，未发气泡」。

---

## 7. 超时与重试

自然间隔 `gap_seconds`：

| schedule | gap_seconds |
|---|---|
| interval | `every_seconds` |
| hourly | 3600 |
| daily | 86400 |
| weekly | 604800 |

实际超时秒数是 `min(86400, max(timeout_seconds 或 gap_seconds, gap_seconds))`。未声明超时时，周任务的 worker 上限是 86400 秒，不是 7 天。

超时杀掉 worker，记 `outcome = timed_out`。

`max_retries` 只对 `runtime_failure` 和 `timed_out` 生效。worker 完成并交来「没做完」的 `worker_message`，记 `completed`，不重试。已经落到 artifact 的 `space_action` 不因为同一次 run 再执行一遍。

重试使用同一个 `run_id` 的尝试序号。耗尽后注入一条 `outcome` 为最后一次失败的 handoff。

---

## 8. 同一任务重叠

修订 ADR-0263 C1 对 `CronJob` 的「未取得锁则 SKIP、不排队」。锁、心跳、stale 收割、单任务失败不杀 tick，仍按 0263。

同一 `job_id`：

- 已有运行中的 run 时，新的到点不杀掉它，也不平行再起一个 worker。
- 排队槽只有一个。新的到点写入这个槽。槽里更早的待跑项取消，记 `superseded`。
- 运行中的 run 结束后，若槽里有待跑项，立刻起那一次。没有则等待下一次 `next_run`。
- `superseded` 不产生 handoff，不重试。

0264 的 `ProactiveJob` 仍按自身的 tick 与裁决。它不进入这个排队槽，也不出现在「即将到来」。

---

## 9. 谁可以改任务

| 动作 | 谁 | 门槛 |
|---|---|---|
| `cron.add`，用户本轮明确说了周期 | 模型 | 直接写入。卡片上立刻可见 |
| `cron.add`，用户没说周期，模型认为该有 | 模型 | 直接写入。`report` 缺省 `anomalies_only`。卡片上立刻可见 |
| 改 `title`、`body`、`report`、`enabled` | 模型或卡片上的用户 | 直接写入 |
| 改 `schedule` 或 `timezone`，从而改变下一次触发 | 模型 | 审批卡片。用户点了才写。未点则保持原定义 |
| 同上 | 卡片上的用户 | 用户的保存就是批准，不再弹卡片 |
| `cron.remove` | 模型 | 审批卡片 |
| `cron.remove` | 卡片上的用户 | 用户的删除就是批准 |

审批未完成时定义不变。重复的审批请求以同一 `job_id` 加同一目标定义为幂等键，不叠多张卡片。

用户只在对话里答应一次「到点跑」，得到的是 `execution.kind = agent` 的周期任务，不是只跑一次。把周期任务改成另一档 schedule，按上表重新审批。

---

## 10. 即将到来

右侧 tab 的注册点是 `useBusinessWorkingSidebarTabs`。key 为 `upcoming`，标签为「即将到来」。持久改动写在 `deploy/lobehub/patches/`，不写进 gitignore 的 `lobehub-ui/` 源码。

tab 打开时请求与 `cron.list` 相同的投影。浏览器不计算下次触发。请求失败时显示错误，不显示本地猜测的时间。

每张卡片展示 `title`、schedule 的人话、`next_run_local`、`enabled`、最近一次 `delivery`（`never`、`silent`、`delivered`、`failed`、`superseded`）。用户可以改 §9 允许卡片改的字段。保存调用 `cron.update` 的同一存储写入口。

`delivery = silent` 的卡片仍然显示最近一次运行时间。没有气泡不等于没有跑。

---

## 11. 明确不采纳

- 命名空间 `smart`。它不说明调用进了哪一个 runtime。
- 把 ADR-0255 的 15 个 `muse.*` 工具整包复制为 `lca.*`。文件、shell、记忆已经有域。
- 用 `ProactiveJob.content` 充当 worker 指令。那份字符串是投递给用户的正文。
- 在浏览器里用 cron 表达式推下次触发。
- 用 exec 死循环代替调度器。
- 让 cron worker 复制父聊天。那是 §3.2 的 subagent，而且本 ADR 不在本轮实现它。
- 用 ADR-0264 的 `decide` 在 worker 报告生成之前判定静默。

---

## 12. 所有权与外部后果

| 事实 | 所有者 | 外部可见后果 |
|---|---|---|
| `CronJob` 定义 | cron 存储 | 卡片、`cron.list`、worker 的 `body` |
| `next_run_local` | `next_run` 纯函数 | 卡片上的时间 |
| run 记录 | cron 存储，只追加 | 卡片上的最近一次结果。压缩父对话不删除 |
| handoff 文本 | runtime 注入父的下一轮 | 父能决定说或不说 |
| 可见气泡 | 父的回复 | 出现在 `delivery_targets` 的 chat |
| 无气泡 | `lca.nothing_to_do` | 该 chat 没有新气泡。卡片记 `silent` |
| 审批点选 | 用户 | 点选前定义不变 |

---

## 13. 失败语义汇总

| 事件 | 结果 |
|---|---|
| 未知 timezone、非法 schedule、侧聊跨 chat 投递 | `cron.add` / `cron.update` 拒绝，存储不变 |
| 重复 id 的 `cron.add` | 返回现有记录，不修改 |
| worker 超时 | 杀进程，按 §7 重试或 handoff |
| worker 报告未完成 | `completed`，不重试，handoff |
| 排队槽被更新的到点替换 | 旧排队项 `superseded`，无 handoff |
| 持锁进程崩溃 | 按 ADR-0263 stale 收割后，槽里的待跑项可以启动 |
| `nothing_to_do` 出现在用户提问轮 | 工具错误回注，不静默 |
| 父既不回复也不调用 `nothing_to_do` | 本轮不结束为静默。runtime 继续等待 |
| 列表接口失败 | 卡片区显示错误，不显示推算时间 |

---

## 14. 验收

实现按这个顺序提交。前一条没有测试之前，不开始下一条。

1. `next_run` 对小时、日、周、间隔和 naive datetime 的字面断言通过。`CronJob` 拒绝双 schedule、非法 timezone、侧聊跨 chat、`space_action` 带投递目标。
2. `cron.list` 投影的 `next_run_local` 与 `next_run` 相同。停用任务仍带时间，并标停用。
3. 右侧 `upcoming` tab 只渲染该投影。改标题保存后，再次 `cron.list` 读到新标题。
4. 模型经 `cron.add` 写入的记录与卡片读到的是同一文件。
5. 到点的 `agent` worker 初始消息含 `body`，不含父聊天原文。完成后父的下一轮能看到 `ScheduledHandoff`。
6. 父调用 `lca.nothing_to_do` 后，目标 chat 没有新气泡，卡片 `delivery = silent`。用户提问轮调用该工具得到错误。
7. 同一任务运行中再次到点，只保留最新排队项。运行中的那次不被杀掉。
8. 超时重试不超过 `max_retries`。worker 的「没做完」不增加尝试次数。
9. 模型 `cron.remove` 在审批点选前不删除文件。

§3.1、§3.2、§3.3 的实现不在这 9 条里。它们的契约以本 ADR 为准，另有实现时不得改种子和回注的形状。

---

## 15. 与现有记录的边界

今天生产路径上没有 tick 调用 `ProactiveScheduler` 或 `RoutineSchedulerService`。助理 jobs 路由返回 501。本 ADR 不把这三套未接线的行为宣称为即将到来的数据源。

即将到来的数据源从本 ADR 被实现的那一次提交开始，只是 `CronJob` 投影。
