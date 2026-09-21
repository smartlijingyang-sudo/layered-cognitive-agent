# Agent Note: 机器平面路径授权归 CapabilityGrant,PlaneRef.root 降为工作目录锚点

Status: proposed

> 本 Note 钉机器平面(UserMachine)的一条 seam 边界:路径授权由谁判定、以什么类型表达、
> 失败如何收口。它实施 [ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §1.1 / §3.2 / §4.3
> 已决定的四边界划分,不新开机制。同意边界仍归
> [ADR-0078](../../../adr/0078-hil-approval-state-machine.md)。

## Problem

用户机器上的一次只读请求以 run 失败收场,全程没有出现任何人工审批提示。run `run_5fd426ea0367`
的目标是「本机的clash代理现在是什么情况 状态 配置等」。模型先用 shell 列出了
`C:\Users\li\AppData\Roaming\io.github.clash-verge-rev.clash-verge-rev\` 下的配置文件,随后用
`local_readFile` 读取同样这些路径,四次调用全部返回 `waiting for human approval`,run 记 failed。
journal 里没有 `approval.persisted.v1`,没有 `session.checkpoint.v1{waiting_input}`,也没有
`intervene.interrupt`。

机器平面的路径授权当前有两个来源,它们对同一件事给出不同答案,而生效的那个不是
[ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) 指定的那一个。

第一个是 `lca/infrastructure/runtime_plane/scope/scope.py`,以单一 `PlaneRef.root` 为界,越界抛
`ApprovalPendingError`。第二个是 [ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §3.2
的 `CapabilityGrant.path_prefixes`,由 `MachineLocalExecAdapter` 校验,越界产出
`EffectReceipt(error_kind="scope_violation")`。生产路径只经过第一个。

由此产生三个结构性后果。授权判定用同意信号表达,而 §1.1 明确写着四个边界不能用其中一层替代
另一层。同意信号没有消费者,于是「需要人批准」被折成「run 失败」,用户既看不到请求也无法批准。
而实际生效的那个判定在 Windows 上可被路径穿越绕过,它守不住它声称要守的东西。

## 当前实现状态

以下均为当前代码的可观察状态。

| 事实 | 位置 |
|---|---|
| `CapabilityGrant.path_prefixes` 与 `EffectReceipt.error_kind="scope_violation"` 已在 contracts 层 | `lca/contracts/models/core/execution/local_exec.py:51,68` |
| `MachineLocalExecAdapter` 校验 grant 过期与路径前缀,产出 receipt | `lca/infrastructure/computer/machine/adapter.py:44-63` |
| 该适配器在 `lca/` 下没有构造点;`path_prefixes` 的消费者只有它与两个测试替身 | `lca/infrastructure/computer/fake/{companion,sandbox}.py` |
| 工具面直接构造 `MachineComputer`,绕过 LocalExecPort | `lca/infrastructure/tools/lca_computer/__init__.py:107` |
| 8 个文件 op 都过 `raise_if_out_of_scope`,`run_command` 不过 | `lca/infrastructure/computer/machine/machine.py:31-139` |
| `_normalize` 对 Windows 用 `PureWindowsPath`,它不折叠 `..`;对 POSIX 用 `os.path.normpath`,它折叠 | `lca/infrastructure/runtime_plane/scope/scope.py:73-78` |
| `F:\下载\..\secret.txt` 判定为不需授权,`/home/lca/../.ssh/id_rsa` 判定为需要 | 同上,`path_needs_approval` |
| 适配器用 `posixpath.normpath` 比对前缀,Windows 穿越同样通过 | `lca/infrastructure/computer/machine/adapter.py:54-56` |
| 适配器 `_dispatch` 覆盖 4 个 op,`MachineComputer` 有 11 个 | `lca/infrastructure/computer/machine/adapter.py:96-109` |
| 提示词向模型承诺「Paths outside the working root ... require user approval」 | `lca/infrastructure/runtime_plane/prompts/machine_system_role.md` |

`scope.py` 的模块 docstring 声称 "Collapse `..`"。该声称对 POSIX 成立,对 Windows 不成立。
`tests/scenario/plane/test_plane_bindings.py::test_dotdot_escape_needs_approval` 只覆盖 POSIX。

## Proposal

路径授权将收归 LocalExecPort 边界,由 `CapabilityGrant.path_prefixes` 判定,以
`EffectReceipt(error_kind="scope_violation")` 收口。`PlaneRef.root` 将只承担工作目录锚点职责:
解析相对路径、决定附件落点与 `outputs_dir`。`scope.py` 将保留 `resolve_plane_path` 作为纯规范化
函数并修掉 Windows 的 `..` 折叠,其授权判定与 `ApprovalPendingError` 抛出将删除。

第一性原理是 [ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §1.1 的四边界。
`root` 回答的是执行边界的问题:哪个路径、哪个工作目录实际执行。它不回答授权边界的问题:
这个 job 被允许碰哪些路径前缀。把两个问题压进同一个字段,就是当前 seam 的病根。

### 边界归属

| 关注点 | 归属 | 类型 | 失败语义 |
|---|---|---|---|
| 相对路径解析、附件落点、产物目录 | `PlaneRef.root` / `outputs_dir` | 执行边界,纯数据 | 无判定,不失败 |
| 这个 job 能碰哪些路径前缀、哪些命令类 | `CapabilityGrant.path_prefixes` / `command_class` | 授权边界,控制面签发,Companion 本地复核 | `EffectReceipt(error_kind="scope_violation")` |
| 什么时候必须停下来等人批 | [ADR-0078](../../../adr/0078-hil-approval-state-machine.md) HIL 状态机 | 同意边界 | `TerminalOutcome(WAITING_INPUT)` + `approval.persisted.v1` |
| 请求、批准、执行、结果如何重放 | `Session.append` | 事实边界 | receipt 追加,不可变 |

授权失败是一次有类型的回执,不是一个逃逸的异常。同意是授权策略的输出,不是授权判定的
表达方式。二者的时序是:先判授权,授权通过后再由策略决定是否需要同意。

### 只读与写入的策略不对称

[ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §4.3 要求 `run_command`、写入受保护
路径、网络访问、凭证使用和后台任务默认 `WAITING_APPROVAL`,低风险只读操作可由策略降级。
这条不对称将落成一个数据驱动的策略对象,由控制面在签发 grant 时消费,而不是落成适配器里的
条件分支。策略对象的输入是 `operation` 与目标路径相对 grant 的位置,输出是
`allow | scope_violation | needs_approval` 三态。

### 提示词只陈述 grant

`machine_system_role.md` 将陈述本次 job 的 grant 范围与工作目录,不再陈述一条运行时并不遵守的
越界审批规则。渲染仍走
[执行环境目录与平面提示词策略](../../implemented/seam/2026-09-21-execution-environment-catalog-and-plane-prompt-strategy.md)
的 `MachinePlaneStrategy`,模板是唯一的字符串来源。

### root 与 workspace 是一个事实

`ExecutionEnvironment` 同时声明 `root` 与 `workspace`,而 `environment_from_plane()` 只填 `root`,
`DeviceEnvironmentProvider` 只填 `workspace`。`bind.py::plane_ref_for_device` 把 `device.workspace`
塌进 `PlaneRef.root`。同一台机器经两条投影路径会给出两个名字、两组各填一半的字段。本提案将
`workspace` 定为设备上报的工作目录这一唯一事实,`root` 定为它在本次 run 的解析结果,并要求两条
投影路径填齐同一组字段。

### 业界对照

Codex 把 sandbox mode 与 approval policy 写成两个正交旋钮,前者管技术上能碰什么,后者管什么
时候必须停下来问;工作区是当前目录加临时目录;越工作区的编辑要审批;`.git`、`.agents`、
`.codex` 在可写根内仍只读。Claude Code 的只读工具在工作目录与 `additionalDirectories` 内免审批,
规则按 deny、ask、allow 顺序求值,`Read(./.env)` 这类 specifier 单独管秘密文件,
`bypassPermissions` 下 `rm -rf /` 与 `rm -rf ~` 仍作为熔断提示。这与
[ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §1.1 的划分一致:grant 对应
sandbox mode,HIL 对应 approval policy。LCA 两者都已设计,其中一个尚未接线。

## Alternatives considered

### Why not 只修 HITL 暂停消费者,保留 root 牢房?

[graph HITL 暂停未被执行](../../implemented/seam/2026-09-18-graph-hitl-pause-not-honored.md)
已经为 `askUserQuestion` 修过暂停消费者,那条修复是本提案的前置条件而非替代品。只修暂停会把
授权判定继续留在同意信号里,ADR-0246 §1.1 的四边界仍然被压成两层,而且越界读取仍要一次人工
点击才能读一个用户已经授权的本机文件。代价是每换一类工具就要再修一次同一条缝。

### Why not 把 root 改成 home 或整盘,让授权范围自然变大?

这能修掉当次失败,但它继续用执行边界的字段表达授权边界。整盘 root 使 grant 失去意义,
`path_prefixes` 永远等于全盘;home root 只是把牢房换大一号,越界读取仍然要么被挡要么穿越。
代价是 ADR-0246 §3.2 的「默认拒绝、Grant 不得扩大到任意路径」无法实施。

### Why not 在 `MachineComputer` 里补齐 `run_command` 的路径检查?

`run_command` 的参数是命令行字符串,不是路径。要在适配器内守住它就得解析 shell 语法,
那正是 Claude Code 文档写明会失败的做法:复合命令、wrapper、变量展开都能绕过前缀匹配。
[ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §3.2 为此准备了
`command_class` 与 `command_allowlist`。代价是在错误的层里重造一个 shell 解析器。

### Why not 维持现状?

现状下用户机器上的正常只读请求会静默失败,Windows 路径穿越可绕过唯一生效的守卫,
而 ADR-0246 标注的 Implemented (M1–M4) 与生产路径不符。代价是每一次本机任务都要靠 shell
绕开文件工具,授权层形同不存在。

## Acceptance criteria

同一目标的 run 读取 grant 内路径时完成,journal 无 `scope_violation`。

读取 grant 外路径时,journal 出现 `approval.persisted.v1` 与 `session.checkpoint.v1{waiting_input}`,
`GET /runs/{id}` 的 status 为 `input-required`,run 不记 failed。`POST /runs/{id}/answer` 批准后
同一 run_id 续跑至完成。

`F:\下载\..\secret.txt` 在 root 为 `F:\下载` 的 Windows 机器平面上被判为 grant 外,POSIX 与
Windows 两条路径的判定一致。

`run_command` 与 8 个文件 op 经过同一个授权判定点;`lca-ops why <capability>` 显示路径授权归属
LocalExecPort 边界。

`scope.py` 不再 import `ApprovalPendingError`;`grep -rn raise_if_out_of_scope lca/` 无命中。

## Risks

接线 LocalExecPort 会改变工具执行路径。适配器 `_dispatch` 当前只覆盖 4 个 op,`MachineComputer`
有 11 个;接线前必须先补齐映射,否则 7 个 op 会返回 `unknown`。

grant 的签发方尚不存在。控制面在签发能力就位前,默认拒绝会让所有机器 run 失败。因此迁移必须
先有默认 grant 构造点,再接线端口,最后删除 `scope.py` 的授权职责。顺序颠倒会造成一次全量
机器面不可用。

策略对象引入一个新的配置面。它需要 owner 与 delete-when:若三态输出长期只有 `allow` 与
`needs_approval` 两种被使用,`scope_violation` 分支应删除而不是保留。

撤回条件沿用 [ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §9。若产品永久只做
云端 Sandbox,本 Note 随该 ADR 一并 Superseded。

## Migration plan

四步,每步以一个可观察检查收尾。

1. 修 `resolve_plane_path` 的 Windows `..` 折叠,改用 `ntpath.normpath`,补 Windows 穿越回归测试。
   检查:两个平台对同一穿越形状给出同一判定。
2. 补齐 `MachineLocalExecAdapter._dispatch` 到 11 个 op,并把前缀比对改为平台感知。
   检查:替换测试对每个 op 都产出 receipt 而非 `unknown`。
3. 引入默认 grant 构造点与三态策略对象,把工具面从 `MachineComputer` 切到 LocalExecPort。
   检查:现有机器 run 全部通过 grant 路径,journal 出现 receipt。
4. 删除 `scope.py` 的授权职责与 `ApprovalPendingError` 抛出,改写 `machine_system_role.md`。
   检查:`grep -rn raise_if_out_of_scope lca/` 无命中,提示词不再陈述越界审批规则。

第 3 步之前不删任何旧路径。第 4 步与第 3 步同 PR 收口,不留跨 PR 的兼容分支。

## Open questions

默认只读 grant 的宽度是产品决定,不是实验能定的。三个候选:仅 workspace 加 outputs 加临时目录;
workspace 加 home 加临时目录并对秘密路径设 denylist;整盘只读并对写入设闸。第二个与 Codex 的
workspace-write 加 praison 式 `external_dir` ask 最接近,也让当次 clash 配置读取经一次批准即可
完成。本 Note 按第二个撰写。

秘密路径 denylist 归 grant 签发方还是归策略对象。二者都能表达,归属决定它是否随 job 变化。

## Related

- [ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §1.1 四边界、§3.2 Grant、§4.3 HIL 降级、§9 删除条件
- [ADR-0078](../../../adr/0078-hil-approval-state-machine.md) 同意边界与 HIL 状态机
- [执行平面设计](../../../design/2026-08-14-execution-planes-design.md) §5.5 本机可写根、§14 开放问题 1
- [graph HITL 暂停未被执行](../../implemented/seam/2026-09-18-graph-hitl-pause-not-honored.md) 暂停消费者,本提案前置条件
- [HIL resume 必须重绑 RunAmbit](../../implemented/seam/2026-09-05-hil-resume-rebinds-ambit.md) 恢复侧 ambient 真值
- [执行环境目录与平面提示词策略](../../implemented/seam/2026-09-21-execution-environment-catalog-and-plane-prompt-strategy.md) `ExecutionEnvironment` 与 `MachinePlaneStrategy`

邻接缺陷,不在本 Note 范围:`EnvironmentKind(plane.kind.value)` 对 `PlaneKind.POOL_WORKER` 抛
`ValueError`,两个闭集对同一概念给出不重合的成员;`ExecutionEnvironment.capabilities` 在两条构造
路径上都未填充。二者各自成一条 Note。

## References

[1]: https://code.claude.com/docs/en/permissions "Claude Code — Configure permissions"
[2]: https://learn.chatgpt.com/docs/agent-approvals-security "OpenAI Codex — Agent approvals & security"
