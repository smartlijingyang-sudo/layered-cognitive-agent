# Agent Note: 机器平面路径授权归 CapabilityGrant,PlaneRef.root 降为工作目录锚点

Status: implemented

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

修复前,机器平面的路径授权有两个来源,它们对同一件事给出不同答案,而生效的那个不是
[ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) 指定的那一个。`scope.py` 以单一
`PlaneRef.root` 为界,越界抛 `ApprovalPendingError`;而 ADR-0246 §3.2 的
`CapabilityGrant.path_prefixes` 由 `MachineLocalExecAdapter` 校验,该适配器在生产路径上没有
任何构造点。实际生效的判定在 Windows 上还可被路径穿越绕过,而 `run_command` 完全不受检查。

## Decision

授权判定由 `lca/infrastructure/runtime_plane/access` 拥有。`decide_access(operation, *, scope,
plane, paths, command)` 返回一个类型化的 `AccessDecision`,不抛异常、不做 I/O。`AccessScope`
是判定输入,由平面直接投影:读范围是工作根加用户 home,写范围限工作根内,凭据路径读要同意、
写直接拒绝,`run_command` 仅当每个子命令都在只读白名单内才放行。`CapabilityGrant` 保留给
控制面签发路径,`access_scope_of` 把 grant 单向投影成 `AccessScope`。

路径代数是纯函数,位于 `lca/infrastructure/runtime_plane/paths`,对 Windows 用 `ntpath.normpath`
折叠 `..`,对 POSIX 用 `os.path.normpath`,两条路径判定一致。ambient 平面绑定位于
`runtime_plane/bindings`。`runtime_plane/scope` 已删除,不再有任何 import。

`MachineComputer` 的 11 个操作全部经过同一个授权点。允许则执行;拒绝返回
`ComputerOpResult(state.error_kind="scope_violation")`;需要同意返回
`approval_required` 并携带 `approval_request` 结构,由同意边界决定是否暂停。
`think.decision.parse` 与 `DefaultDecisionClassifier` 通过 `machine_calls_need_approval` 把机器
平面的同意需求并入 `Decision.needs_approval`,走
[ADR-0228](../../../adr/0228-plan-intervene-delegate-subgraphs.md) 的图路径。

`machine_system_role.md` 陈述 grant:工作根加 home 可读,写限工作根内,白名单之外的命令需要
同意。它不再陈述一条运行时并不遵守的越界审批规则。`root` 只承担工作目录锚点职责,
`workspace` 是设备上报的工作目录这一唯一事实。

## Alternatives considered

### Why not 只修 HITL 暂停消费者,保留 root 牢房?

[graph HITL 暂停未被执行](../../implemented/seam/2026-09-18-graph-hitl-pause-not-honored.md)
为 `askUserQuestion` 修过暂停消费者,那条修复是本方案的前置条件而非替代品。只修暂停会把
授权判定继续留在同意信号里,ADR-0246 §1.1 的四边界仍然被压成两层,而且越界读取仍要一次人工
点击才能读一个用户已经授权的本机文件。代价是每换一类工具就要再修一次同一条缝。

### Why not 把 root 改成 home 或整盘,让授权范围自然变大?

这能修掉当次失败,但它继续用执行边界的字段表达授权边界。整盘 root 使 grant 失去意义,
`path_prefixes` 永远等于全盘;home root 只是把牢房换大一号。代价是 ADR-0246 §3.2 的「默认拒绝、
Grant 不得扩大到任意路径」无法实施。

### Why not 在 `MachineComputer` 里补齐 `run_command` 的路径检查?

`run_command` 的参数是命令行字符串,不是路径。在适配器内守住它就得解析 shell 语法,那正是
Claude Code 文档写明会失败的做法:复合命令、wrapper、变量展开都能绕过前缀匹配。本方案用
`command_class` 与 `command_allowlist`,按子命令拆分匹配。代价是在错误的层里重造一个 shell
解析器。

### Why not 维持现状?

现状下用户机器上的正常只读请求会静默失败,Windows 路径穿越可绕过唯一生效的守卫,而
ADR-0246 标注的 Implemented (M1–M4) 与生产路径不符。代价是每一次本机任务都要靠 shell
绕开文件工具,授权层形同不存在。

## Consequences

原本失败的那次读取现在判定为 `ALLOW`:`C:\Users\li\AppData\Roaming\...` 位于默认读范围
(工作根加 home)内。`run_5fd426ea0367` 的场景可直接复现验证。

`ApprovalPendingError` 不再从路径层逃逸。授权判定是类型化的数据,消费方把它转成执行、
ADR-0078 暂停或 `EffectReceipt`。

`run_command` 的行为变严。白名单之外的命令(如 `python3 make_pdf.py`)现在需要同意;此前它们
直接执行。测试通过注入自定义 `AccessScope.command_allowlist` 来覆盖这类场景。

Windows 的 `..` 穿越在两个平台上一视同仁地被拒。`PureWindowsPath` 按设计不折叠 `..`,
`ntpath.normpath` 折叠它,与 POSIX 的 `os.path.normpath` 语义对齐。

## Verification

`tests/infrastructure/runtime_plane/test_access_policy.py` 覆盖策略判定与凭据路径。
`tests/infrastructure/runtime_plane/test_access_classify.py` 覆盖 wire 工具名到策略操作的
anti-corruption 层。`tests/scenario/machine/test_machine_computer.py` 覆盖
`MachineComputer` 的类型化拒绝结果。`tests/scenario/machine/test_machine_path_scope.py` 与
`tests/scenario/plane/test_plane_bindings.py` 覆盖路径代数与 Windows 穿越。

机器与 runtime_plane 测试 81 项通过。`tests/scenario/computer` 与
`tests/scenario/execution` 的两条失败在干净 HEAD 上原样复现,不是本方案引入。

## Open questions

默认读范围的宽度已经定为本机 root 加 home。凭据路径的判定落在策略内;归控制面还是策略的
问题仍未定,它决定 denylist 是否随 job 变化。

ADR-0246 M2 的控制面签发仍未接通。`subject_user_id` 在工具构造路径上还没有来源,因此
`AccessScope` 走平面投影路径,`CapabilityGrant` 的签发等待控制面落地。

## Related

- [ADR-0246](../../../adr/0246-user-machine-side-effect-plane.md) §1.1 四边界、§3.2 Grant、§4.3 HIL 降级、§9 删除条件
- [ADR-0078](../../../adr/0078-hil-approval-state-machine.md) 同意边界与 HIL 状态机
- [ADR-0228](../../../adr/0228-plan-intervene-delegate-subgraphs.md) 图级 HITL 中断路径
- [执行平面设计](../../../design/2026-08-14-execution-planes-design.md) §5.5 本机可写根、§14 开放问题 1
- [graph HITL 暂停未被执行](../../implemented/seam/2026-09-18-graph-hitl-pause-not-honored.md) 暂停消费者,本方案前置条件
- [HIL resume 必须重绑 RunAmbit](../../implemented/seam/2026-09-05-hil-resume-rebinds-ambit.md) 恢复侧 ambient 真值
- [执行环境目录与平面提示词策略](../../implemented/seam/2026-09-21-execution-environment-catalog-and-plane-prompt-strategy.md) `ExecutionEnvironment` 与 `MachinePlaneStrategy`

邻接缺陷,不在本 Note 范围:`EnvironmentKind(plane.kind.value)` 对 `PlaneKind.POOL_WORKER` 抛
`ValueError`,两个闭集对同一概念给出不重合的成员;`ExecutionEnvironment.capabilities` 在两条构造
路径上都未填充。二者各自成一条 Note。

## References

[1]: https://code.claude.com/docs/en/permissions "Claude Code — Configure permissions"
[2]: https://learn.chatgpt.com/docs/agent-approvals-security "OpenAI Codex — Agent approvals & security"