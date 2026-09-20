# ADR-0246 — 用户机器副作用平面（User-Machine Side-Effect Plane）

## 状态

**M1 Implemented — 2026-09-20**

Refines: [ADR-0044](0044-code-sandbox-adapters.md)、[ADR-0050](0050-run-bound-sandbox-runtime.md)、[ADR-0051](0051-run-workspace-plane.md)、[ADR-0076](0076-six-plane-capability-layout-and-substitution-test.md)、[ADR-0078](0078-hil-approval-state-machine.md)、[ADR-0186](0186-session-as-event-ssot.md)、[ADR-0200](0200-p1-agent-gateway-bridge.md)、[ADR-0206](0206-information-graph-kernel.md)。

Related seams（挂缝，不另起 Runtime）：

- `lca/infrastructure/computer`：`MachineComputer`、`SandboxComputer` 和 Computer ops；
- `lca/infrastructure/device_hub`：现有设备通道；
- Tool / Body 执行面与 HIL 审批（ADR-0078）；
- Agent Gateway 投影面（ADR-0200）；
- `Session.append` 事实轨（ADR-0186）。

## 0. 决策摘要

网页是控制和同意界面，不是用户操作系统的执行权威。用户本机的文件、Shell、Git 和办公脚本等副作用，必须由**已配对的本机执行器**在本地施加边界后执行；浏览器页面不得直接持有长期本机凭证，也不得把平台沙箱伪装成用户磁盘。

LCA 采用一个统一的 **Computer/LocalExec Port**，将执行目标显式建模为 `Sandbox`、`UserMachine` 或 `PoolWorker`。Port 的调用、审批、幂等、租约、结果和审计语义保持不变，只有 Provider 与 transport 可替换。当前 `MachineComputer` 已符合“只依赖 `MachineTransport`、不持有 Sandbox、不做路径重映射”的基础方向；本 ADR 不新建第二个 Interpreter、`GraphRuntime`、Loop 或平行事实轨。

产品默认使用托管的 Sandbox/PoolWorker。只有用户明确选择“使用我的电脑”时，才路由到 `UserMachine`。主路径是 **Local Companion + 出站长连接 + Device Code 配对**。浏览器 File System Access 仅作为零安装的受限读写补充；Remote Tunnel/SSH 是 Companion 的 transport 选项，不是另一套业务语义。

## 1. 第一性原理与问题边界

### 1.1 副作用的四个不可合并边界

一个本机副作用请求同时包含四类不同问题：

| 边界 | 要回答的问题 | LCA 权威位置 |
|---|---|---|
| 执行边界 | 哪个 OS、哪个路径、哪个用户实际执行？ | Paired Companion / Sandbox / Worker |
| 授权边界 | 哪些操作、路径、命令类和时长被允许？ | Capability Grant + 本地强制执行 |
| 同意边界 | 什么时候必须暂停并等待人批准？ | ADR-0078 HIL 状态机 |
| 事实边界 | 请求、批准、执行和结果如何重放与审计？ | `Session.append`；Gateway 只做投影 |

不能用其中一层替代另一层。用户点击“允许”不能把任意 Shell 变成安全操作；沙箱限制也不能替代对高风险外部副作用的明确同意。Claude Code 和 Codex 都将 sandbox 与 approval 作为正交控制；行业实践也把权限规则放在宿主产品而不是模型提示词中。[1] [2] [3]

### 1.2 本 ADR 负责与不负责

本 ADR 负责 Web Agent 如何获得一个可治理的用户机器执行目标，以及如何与现有 Computer、HIL、Gateway 和 Session 语义对齐。它不规定 Companion 的 UI 框架、安装包技术、具体云厂商，也不把 PowerShell 定义成唯一 Shell。

本 ADR 不解决“让浏览器直接执行本机命令”。这个问题的正确答案是拒绝该形态：浏览器 Origin 适合发起选择和同意，不适合作为长期 OS 凭证的保管者或任意命令的执行者。

## 2. 业界方案与可迁移结论

### 2.1 方案谱系

| 方案 | 行业事实 | 适合的 LCA 位置 | 结论 |
|---|---|---|---|
| 本机 Companion | VS Code Remote Tunnels 由主机和客户端以同一账号认证，双方主动出站，服务端通常无需开放入站监听；连接上再承载端到端加密通道。[4] | `UserMachineProvider` 的默认实现；出站连接是 transport | **采用** |
| 浏览器受限文件能力 | File System Access 需要安全上下文和用户手势；句柄权限可再次询问，写入已有文件需要明确权限。它只覆盖选定文件/目录，不提供通用 Shell。[5] | `BrowserFileProvider` 的只读或受限读写补充 | **采用为补充，不进 Shell 面** |
| Remote SSH / Tunnel | VS Code Remote、JetBrains Gateway 等把执行环境指向远端主机。它解决连接，不自动解决最小权限、审批和审计 | Companion 的 transport；或高级用户的显式 Provider | **不升格为业务抽象** |
| 托管 Sandbox / Pool / VDI | Codespaces 在 VM 上运行 Docker 开发容器，用户对外层主机只有有限访问；这与用户个人电脑是不同执行边界。[6] | 默认 Provider | **默认优先** |
| 企业 MDM / 常驻 Agent | 企业通过 MDM 预装和升级 Agent，用户只绑定账号并授予范围 | Companion 的分发与组织治理 | **M4 支持** |
| 无配对网页桥、页面内 PowerShell、服务端保存 OS 密码 | 把 Origin、长期凭证或服务端变成 OS 权威，无法形成清晰的主体、范围和撤销边界 | 无 | **拒绝** |

业界的共同结构不是“网页拿到本机 Shell”，而是四段组合：受约束的执行器、显式的授权、必要时的人批准，以及可撤销的连接身份。Tailscale 的 ACL 进一步说明，最小权限、默认拒绝、方向性和设备本地强制执行应成为连接层的默认心智模型。[7]

### 2.2 配对为何采用 Device Code

Companion 可能没有可靠的本地回调窗口，也不应嵌入用户的长期 Web 会话。GitHub Device Flow 已验证了适合无头设备的模式：设备申请短期 `device_code` 和用户可见 `user_code`，用户在浏览器完成授权，设备按服务端给出的间隔轮询，直到成功或过期。[8]

因此，LCA 的配对只把一次性代码用于建立关系。配对完成后，Companion 保存本地密钥材料，控制面保存可吊销的机器凭证；二者均不能替代每次 Job 的短期 Grant。任何代理授权或动态回调都必须绑定客户端、精确校验 redirect URI、保留 CSRF 防护，并记录用户同意事实，以避免 confused deputy。[9]

## 3. LCA 统一模型

### 3.1 Port 与 Provider

收束现有 Computer 抽象为以下语义，不要求一次性改变所有公共类名：

```text
LocalExecPort.execute(
  target,
  operation,
  normalized_args,
  grant,
  approval,
  idempotency_key,
  lease,
) -> ComputerOpResult + receipt
```

`target` 必须显式包含 `kind`、`id`、`label` 和能力摘要。`operation` 是闭集或经注册的操作类型，例如 `read_file`、`write_file`、`run_command`、`git`，而不是让模型直接拼出未治理的 transport 消息。`normalized_args` 包含规范化后的路径、工作目录、参数、超时和资源限制。

Provider 只负责把 Port 请求映射到执行器：

```text
SandboxComputer       -> Run-bound Sandbox
PairedCompanionProvider -> 已配对 UserMachine
RemoteTunnelProvider  -> Companion 的 Tunnel/SSH transport
PoolWorkerProvider    -> 团队共享或内网 Worker
BrowserFileProvider   -> 用户手势授予的文件句柄
```

替换测试要求：对同一 `operation` 更换 Provider 后，审批状态、Journal 事件形状、幂等重放和错误分类保持一致。Provider 不得把失败静默转换成另一个目标的成功。

### 3.2 Grant 是能力，不是登录凭证

每个 Job 必须携带短期、窄范围的 `CapabilityGrant`。最小字段为：

```text
subject: user_id + machine_id
resource: path prefixes / repository / network domains
operations: read_file | write_file | run_command | git ...
command_policy: allowlist or command-class policy
expires_at: short TTL
approval_binding: approval_id and requested scope
request_digest: normalized request hash
job_id + idempotency_key
```

控制面负责签发、吊销和审计 Grant；Companion 必须在本地再次校验主体、目标、范围、TTL、请求摘要和租约。默认拒绝。Grant 不得扩大到任意路径、任意命令或无限期后台进程。控制面不得保存用户 Windows/macOS/Linux 密码，也不得把浏览器 token 作为 Companion 的执行凭证。

### 3.3 状态与事实

配对状态为 `UNPAIRED → PAIRING → PAIRED → REVOKED`；在线状态是独立的租约视图，不能被误写成授权事实。Job 至少经过：

```text
REQUESTED → WAITING_APPROVAL → APPROVED → DISPATCHED
  → EXECUTING → COMPLETED | FAILED | CANCELLED | EXPIRED
```

所有状态转换、批准主体、Grant 摘要、Provider/target、开始与结束时间、退出码和脱敏 stdout/stderr 摘要都进入 `Session.append`。Gateway 只投影机器列表、审批卡片和进度。输出正文可能被截断或丢失，但 receipt、exit、错误分类和摘要必须可审计。

`idempotency_key` 绑定规范化请求摘要。Companion 对重复 Job 必须返回原 receipt 或明确的 `already_completed`，不得因控制面重试而再次执行。租约失效后，控制面必须把 Job 标成过期；是否能杀死正在运行的子进程由 Companion 返回确定结果，不能伪造取消成功。

## 4. 推荐产品组合与路由

1. **默认路由到 Sandbox/PoolWorker。** 能在平台边界内完成的工作不下发用户机器。
2. **显式路由到 UserMachine。** 工具描述必须同时展示目标名称、机器标签、路径范围和能力标签；模型不能通过省略 `machine_ref` 获得隐式本机执行。
3. **高风险操作走 HIL。** `run_command`、写入受保护路径、网络访问、凭证使用和后台任务默认 `WAITING_APPROVAL`；低风险只读操作可由策略降级，但仍受 Grant 约束。
4. **浏览器能力只处理用户手势范围。** 目录句柄失效或权限撤回时返回明确错误，不能回落到 Companion 或 Sandbox 并声称完成。
5. **Tunnel/SSH 只改变 transport。** 它不能绕过 Grant、HIL、Journal 或本地策略。

## 5. 安全不变量

| ID | 不变量 |
|---|---|
| I-UMS-1 | 未配对、被吊销或 offline 的 `machine_ref` 必须 fail-loud；禁止静默回落到另一个执行目标。 |
| I-UMS-2 | Companion 凭证绑定 `user_id + machine_id`，可吊销、可轮换，页面 JS 不持久持有。 |
| I-UMS-3 | 所有副作用都有 Grant 范围：目标、路径/命令类、TTL、审批绑定和资源限制。 |
| I-UMS-4 | Grant 在 Companion 本地再次执行；控制面不可仅凭“已批准”绕过本地拒绝。 |
| I-UMS-5 | Sandbox、UserMachine、PoolWorker 在工具 schema 和 UI 中必须可区分。 |
| I-UMS-6 | Job 具备租约和幂等键；重复投递不得重复产生不可逆副作用。 |
| I-UMS-7 | 请求和结果进入 Session Journal；投影丢失不改变事实，敏感输出按策略脱敏。 |
| I-UMS-8 | 浏览器文件句柄只代表用户明确选择的资源，不能被提升为通用 Shell 能力。 |

## 6. 落地切片与验收

### M1：契约收束

保留 `MachineComputer` 作为当前基础适配器，定义 `LocalExecPort` 的请求、Grant、receipt、错误分类和目标标签；补充 `FakeCompanionProvider`。验收包括 offline、deny、expired、timeout、cancel、重复 Job 和 Provider 替换测试。

### M2：配对与控制面

实现 Device Code 配对、`machine_id` 绑定、撤销、心跳和能力宣告。长连接只承载已签名的 Job envelope；控制面不直接执行 OS 调用。验收包括过期代码、错误用户、重复配对、凭证轮换和 revoked machine 的拒绝。

### M3：Companion MVP

先实现一个跨平台可测试的 Companion 核心和单一 `run_command` allowlist。Windows 优先覆盖内网 GitLab 场景；每个命令默认 HIL；本地执行前校验 Grant，执行后返回 receipt 和有限日志。安装包、签名、自动升级和系统服务注册单独治理。

### M4：能力扩展

增加路径 Grant、`git` 专用操作、浏览器文件句柄补充、企业 MDM 预装和 Tunnel/SSH transport。任何扩展都必须复用同一 Port、HIL、Journal 和幂等语义。

## 7. 被否方案与后果

**被否：网页直接执行本机命令。** 浏览器安全模型要求用户手势和显式文件权限，且浏览器能力不能稳定覆盖 Shell、后台任务和企业策略；直接桥接还会把 Origin 变成高价值攻击面。[5]

**被否：只做 Remote Tunnel。** Tunnel 解决可达性，不解决能力范围、审批、撤销、审计和重复执行。因此它只能是 transport。

**被否：所有请求都在用户机器执行。** 这会扩大本机暴露面，并绕过 Sandbox 的成本和合规优势。默认 Sandbox/Pool，显式 UserMachine 才能保持最小权限。

**被否：为本机执行新建 Runtime 或平行 WS 事实面。** 这会破坏 ADR-0206 的单轨和 ADR-0186 的 Session SSOT。Companion 是执行器，不是第二个认知运行时。

正向后果是 Web Agent 获得可选的本机能力，同时保留云端安全基线和 Provider 可替换性。代价是 Companion 的签名分发、跨平台进程治理、撤销恢复和审批 UX。最大的残余风险是模型诱导高影响命令；风险由本地 Grant、allowlist、HIL、资源限制和可审计 receipt 共同收敛，而不是靠隐藏 PowerShell 弹窗。

## 8. 开放问题

1. `LocalExecPort` 是扩展现有 `MachineComputer`，还是在其上增加显式 Provider façade；以不破坏现有 Computer 调用方为约束。
2. Companion 长期密钥采用 mTLS device certificate，还是短期 access token + DPoP；无论选型，均须支持 machine 级撤销和轮换。
3. `device_hub.KernelServeHttpClient` 继续作为 kernel 调试通道，还是仅作为可复用 transport；不得因此获得 UserMachine 的业务语义。
4. 内网 GitLab 场景默认选择本机还是内网 PoolWorker；产品策略必须显式展示数据落点。

## 9. 删除条件

若产品永久只做云端 Sandbox，不再支持用户机器，则本 ADR 标记为 **Superseded**，删除 M2 之后的契约与 Companion 路径。任何临时网页唤起本地脚本的实验桥都必须带 `delete-when` 日期，且不得进入默认工具面。

## References

[1]: https://code.claude.com/docs/en/permissions "Claude Code — Configure permissions"
[2]: https://code.claude.com/docs/en/sandboxing "Claude Code — Configure the sandboxed Bash tool"
[3]: https://learn.chatgpt.com/docs/sandboxing "OpenAI Codex — Sandbox"
[4]: https://code.visualstudio.com/docs/remote/tunnels "Visual Studio Code — Developing with Remote Tunnels"
[5]: https://developer.chrome.com/docs/capabilities/web-apis/file-system-access "Chrome for Developers — The File System Access API"
[6]: https://docs.github.com/en/codespaces/overview "GitHub Docs — What are GitHub Codespaces?"
[7]: https://tailscale.com/kb/1018/acls "Tailscale — Manage permissions using ACLs"
[8]: https://docs.github.com/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps "GitHub Docs — Authorizing OAuth apps: Device flow"
[9]: https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices "Model Context Protocol — Security Best Practices"

---

> 备注：本 ADR 的行业调研记录保存在 `history/` 或任务工作区时，应作为过程材料，不得替代本决策文本中的规范性条款。
