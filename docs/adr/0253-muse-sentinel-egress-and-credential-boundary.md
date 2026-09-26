# ADR-0253: Meta Muse 出站控制面、凭证边界与污点审批

- Status: Proposed
- Date: 2026-09-27
- Deciders: TBD（提交前由架构室填写）
- Relates:
  * [ADR-0050](0050-run-bound-sandbox-runtime.md)：Run-Bound Sandbox Runtime
  * [ADR-0078](0078-hil-approval-state-machine.md)：HIL Approval State Machine（本 ADR 决策四补充其恢复输入）
  * [ADR-0092](0092-durable-session-command-ledger.md)：Durable Session Command Ledger
  * [ADR-0202](0202-transport-ui-env-ssot.md)：Transport/UI env 配置 SSOT（启动期注入）
  * [ADR-0234](0234-effect-pre-dispatch-envelope-check.md)：Effect Pre-Dispatch Envelope Check（授权仍在此闸）
  * [ADR-0246](0246-user-machine-side-effect-plane.md)：用户机器副作用平面（Job `CapabilityGrant`、`request_digest`、Companion 本地强制）
  * [ADR-0251](0251-openmuse-runtime-sandbox-durable-task-evidence.md)：OpenMuse 架构解剖（沙箱文件、审批指纹、任务租约、Takeover、`untrusted_external` 标注）
- Non-goals:
  * 不引入 Meta Muse Spark、Muse 云端 VM，或 Stripe、WhatsApp 一类 Meta 生态能力
  * 不对闭源实现做逆向。机制以公开资料为准，落地时按 LCA 不变量重做
  * 不改 C1、C2、C5、C10、C13 的方向。本 ADR 只收紧执行边界和 Gate 的输入
  * 不重开 ADR-0251 已写的沙箱文件系统、`payload_hash`、任务租约、Takeover
  * 不涉及记忆。记忆仍由 [ADR-0247](0247-agent-memory-knowledge-layer.md) 与 [ADR-0249](0249-cadence-inspired-dual-track-memory-consolidation.md) 覆盖
  * 不新增 `one_time | session | task | time_bounded | perpetual` 时效枚举
  * 不把 eBPF、用户命名空间或 L7 正文检查写成必须实现

---

## 0. 证据分级

Meta Muse 闭源。本 ADR 的强度低于 ADR-0251。决策写不变量。内核手段留到编码前的选型 Note，Note 落 `docs/notes/`，并注明对照的开源实现。

| 级别 | 含义 | 用法 |
| --- | --- | --- |
| E1 | Meta 官方文字。此处为 2026-09-08 研究博客 *How We Built Safety Into Muse*（`https://research.meta.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse`） | 功能契约 |
| E2 | 与 E1 交叉的第三方技术复述（Forkast News 两篇 Sentinel/eBPF 文章，jahanzaib.ai 的 Muse VM 拆解） | 工程图像。与 E1 不一致时以 E1 为准 |
| X | 未公开的策略引擎、具体 eBPF 程序、内部服务实现 | 不得写成 LCA 必须对齐的事实 |

E1 里和本 ADR 有关的三句话：

1. 运行单元的出站流量经 userns、veth 与 eBPF 过滤接到转发代理，由独立控制面 Sentinel 决定允许、拒绝或询问。
2. 运行单元和 worker 只见 `hatch-authd` 签发的 surrogate。Sentinel 在已授权的具体请求上，于网络边界把 surrogate 换成真实凭证。
3. 每个工具进程从干净状态开始。进程读到用户数据后变为污点。干净且命中窄自动放行策略的请求可以不问人。污点或无法核验的进程失去自动放行，退回正常审批。实现手段是 eBPF cgroup 与 LSM hook。本 ADR 采纳触发条件和后果，不采纳必须用 eBPF。

E1 把污点触发写成“读到用户数据”，后果写成“失去自动放行”。这和“外部网页文本不可信，不能当指令”是两件事。后者属于 ADR-0251 决策四。审批弹窗是否必须走另一条网络连接，E1 未写，本 ADR 不把它当 Meta 事实。

---

## 1. Context

ADR-0251 收了沙箱文件、审批指纹、任务租约和 Takeover。下面四条仍开放。

1. **执行模型可控代码的环境仍可能自己出站。** C10 要求副作用走 `cognition → Body → SafeExecutor → Sandbox`。这条约束的是业务代码的调用链。`SandboxBackend` 只规定挂载和读文件，没有“该环境没有默认路由”。沙箱内的 HTTP 客户端或被注入后的代码可以自己建连。宿主上的搜索、HTTP 工具、MCP 和模型供应商调用本来就不进沙箱，不能靠“沙箱后面再加一跳”盖住。
2. **启动期注入之后，明文密钥的持有者未定义。** ADR-0202 规定配置经 `Profile {from_env}` 在 boot 进入。它没有规定 Body、SafeExecutor 或沙箱运行期谁还拿着明文。诱导模型打印环境变量时，明文会从这些进程漏出。
3. **两类数据事实还没有接到 Gate。** 用户私有数据被读过之后，自动放行仍可能继续。外部证据即使标了 `untrusted_external`，也还只是认知层的标签。当前 `lca.contracts.harness.perceive.evidence.Evidence` 没有 `trust_level` 字段，ADR-0251 决策四仍是 Proposed。
4. **批准输入没有排除对话正文。** ADR-0078 的 `ResumeCommand` 要求 `approval_token`。它没有写明这个 token 只能来自审批事件。模型可见正文里的“用户已同意”不能充当批准。

---

## 2. Decision

### 决策一：模型可控的执行环境没有默认路由

归属：沙箱无路由归 ADR-0050 的执行边界，实现落在 sandbox runtime。目的地与方法的授权归 Gate，沿用 ADR-0234 的 `effect.pre_dispatch.envelope_check`。转发器若存在，只做已授权请求的转发，放在 `infrastructure`，不拥有策略。

约束：

1. 执行模型可控代码的 Sandbox 环境没有默认路由，也没有可直接使用的外部网卡。从该环境发起的连接，在网络边界失败。应用层 `try/except` 不算这条边界。
2. 宿主进程里的搜索、HTTP、MCP 和模型供应商调用不进沙箱。它们的出站目的地、端口、方法和范围以沙箱外铸好的 `CommandEnvelope` 为准。执行环境自报的目的地无效。
3. [ADR-0246](0246-user-machine-side-effect-plane.md) 的 UserMachine 使用用户电脑的网卡。已配对 Companion 在本地再次校验 Grant。平台转发器不是 UserMachine 的唯一出口。
4. 转发器不第二次解释策略。策略冲突时以 Gate 的 `Verdict` 为准。
5. 网络命名空间、容器网络或现有代理里选哪一种，由编码前的选型 Note 决定。本决策不要求 eBPF，也不要求检查 L7 正文。

失败语义：连向信封未授权的地址时，连接在网络边界被拒绝，Session 留下拒绝事实。转发器不可用时，出站失败并返回可重试的传输错误，不得改走沙箱直连。

### 决策二：真实密钥只由独立进程按请求摘要兑付

归属：启动期注入仍是 ADR-0202。运行期持有者是与 kernel 进程分离的凭证进程。`contracts` 增加兑付引用的 DTO。引用不是第三套 `CapabilityGrant`。

仓库里已有两份授权对象，本决策都不替换：

| 对象 | 位置 | 职责 |
| --- | --- | --- |
| 信封 `CapabilityGrant` | `lca.contracts.protocols.act.command.envelope` | 单次信封的 `capability` / `scope` / `effect_class`，C5 单调 |
| Job `CapabilityGrant` | `lca.contracts.models.core.execution.local_exec` | ADR-0246 的主体、操作、路径、TTL、`approval_id`、`request_digest` |

约束：

1. 下发给 Sandbox、以及进入模型可见上下文的，是不可单独兑付的引用。兑付同时满足四项：引用、连接器、允许的目的地、ADR-0246 的 `request_digest`。缺任何一项，凭证进程拒绝替换。
2. 明文只存在于独立 OS 进程的内存中。与 kernel 同地址空间的对象不算满足本条。
3. shell、数据库连接串、SSH 和云 SDK 所需的材料不进入子进程环境、沙箱挂载或 Journal。这类调用没有“在 HTTP 边界替换”的路径，因此材料从一开始就不在子进程里。
4. Journal 沿用 ADR-0246 的脱敏回执，只记摘要和错误类别。
5. Provider 把明文写入沙箱环境、参数或挂载文件时，契约测试失败。

失败语义：兑付条件不满足时，凭证进程拒绝，工具回执为确定性错误，不重试。凭证进程不可用时，出站失败，可按传输错误重试，不得把明文退回给 Sandbox。

### 决策三：Gate 分开处理私有数据与不可信证据

归属：工具清单声明读私有数据。`Evidence` 携带信任标记。唯一裁决者是 Gate。感知层只标注。认知层不改写 `CommandEnvelope`。

这是两条约束。

**私有数据。** 工具清单声明本次调用会读取用户私有数据（邮件、日历、联系人、工作区以外的用户文件、用户记忆）。Gate 看到该事实后，本次执行上的网络出站失去自动放行，必须有一份绑在本次 `request_digest` 上的新人工 `Verdict`。下一份工具进程从干净状态开始，直到它自己读到私有数据。污点不写成智能体的永久黑名单。

**不可信证据。** ADR-0251 决策四落地后，网页、第三方 Webhook、外部文档和邮件内容的 `Evidence.trust_level` 为 `untrusted_external`。Gate 不把该字段当作授权来源。出站仍只看 Grant，以及策略要求的人工 `Verdict`。派生进工作区的文件继承来源的信任标记。工作区再读不得洗掉这个标记。

`Evidence.trust_level` 尚未存在。私有数据这条可以先做。不可信证据这条等 ADR-0251 决策四把字段和写入方落地后再接 Gate。在此之前，Gate 不读取一个不存在的字段，也不用“收窄时效”代替人工裁决。

失败语义：应询问却缺少新的人工 `Verdict` 时，执行停在 ADR-0078 的待审批状态。旧的自动放行和同一会话里早先的批准都不能复用到这份 `request_digest`。

### 决策四：批准只来自审批事件

归属：补充 ADR-0078，不新开状态机。

约束：

1. 进入待人工确认时，前端收到的是 Gate 发出的 `Verdict` 事件，事件携带 ADR-0251 决策二的 `payload_hash`。
2. 该事件可以与对话共用 Agent Gateway 连接。事件类型由控制面产生，模型可见正文不能伪造这个类型。
3. 审批卡上的工具、参数和目的地从 `CommandEnvelope` 渲染。模型写的理由只作为不可信说明，不参与判定用户批准了什么。
4. 批准结果是审批卡产生的显式操作，并带回同一个 `payload_hash`。对话正文中的“用户已批准”不改变 Gate 状态。

失败语义：只存在伪造正文、没有匹配 `payload_hash` 的审批操作时，状态保持待审批。`payload_hash` 不匹配或超过 ADR-0251 的窗口时，沿用其 `approval_hash_mismatch_or_expired` 拒绝。

### 决策五：沿用现有授权对象

C5 的三维单调保持不变。本 ADR 不给信封 `CapabilityGrant` 增加 `connector_id` 或 `temporal_scope`。

时效、审批绑定和请求摘要已经在 ADR-0246 的 Job `CapabilityGrant` 上：`expires_at`、`approval_id`、`request_digest`。单次效应的范围已经在信封的 `scope` 上。连接器身份沿用 provider 或 plugin id，以及 Job grant 的 `subject_machine_id` 与 `operation`。

以后若这组字段表达不了“绑到哪个外部账号”或“自动放行维持多久”，再扩展 ADR-0246 的 Job grant。扩展时子授权的时效不得宽于父授权，连接器实例不得超出父授权。未填写的字段表示继承父授权。本 ADR 不引入永久授权。

---

## 3. 落地顺序

顺序是验收依赖，不是排期。

| 顺序 | 范围 | 完成时可以观察到 |
| --- | --- | --- |
| 1 | 选型 Note | Note 选定沙箱无路由的强制手段，并注明开源对照。eBPF 未选中时，决策一仍然成立 |
| 2 | ADR-0078 补充 | 对话中的伪造批准句不能使 Gate 离开待审批 |
| 3 | Sandbox runtime 与宿主出站 | 沙箱内连向未授权地址在网络边界失败。宿主出站只接受信封绑定的目的地 |
| 4 | 独立凭证进程 | 诱导打印环境变量、挂载和回传文本时看不到密钥片段 |
| 5 | Gate | 声明了读私有数据的调用失去自动放行。`trust_level` 落地后再拒绝把不可信证据当授权 |

---

## 4. 验证

1. 沙箱环境内对未授权地址发起连接，失败发生在网络边界。测试不把应用层捕获异常当作通过。
2. 宿主工具携带信封以外的目的地时，Gate 拒绝派发。
3. UserMachine 路径在 Companion 本地拒绝超范围出站，且不回落到平台沙箱。
4. 兑付请求缺少 `request_digest`、连接器或目的地中的任一项时，凭证进程拒绝，Sandbox 内存与 Journal 中无明文。
5. 工具清单声明读取私有数据后，同一 `request_digest` 的网络出站没有新的人工 `Verdict` 时停在待审批。下一份未读私有数据的工具调用仍按原策略自动放行。
6. 不可信内容写入工作区再读回后，信任标记仍在。该标记不使 Gate 把正文当成批准。
7. 对话正文含“用户已批准该操作”时，Gate 保持待审批。审批卡展示的目的地与信封一致。
8. 现有 C5 单调测试继续通过。本 ADR 不修改信封 `CapabilityGrant` 的字段集。

---

## 5. 风险

* 证据弱于 ADR-0251。E2 与 E1 冲突时已在 §0 规定以 E1 为准。落地形状按本节决策，不按第三方文章里的进程名。
* 提示注入仍然存在。本 ADR 使被注入的执行环境拿不到网卡和明文，也使伪造正文不能完成批准。
* 转发和兑付多一次进程间调用。本 ADR 不为低风险只读工具开绕过边界的快路径。
* 凭证进程成为新的高价值目标。它只按四项兑付条件替换，不接受执行环境自选的目的地。
* 决策三的不可信证据分支依赖 ADR-0251 决策四。该字段未落地前，Gate 不实现这条分支。
* 编号以 `docs/adr/README.md` 为准。若 0253 已被占用，顺延编号，不改决策正文的依赖关系。
