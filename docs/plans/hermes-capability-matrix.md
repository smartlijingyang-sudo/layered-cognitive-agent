# Hermes Agent 能力补齐矩阵

本文用于跟踪 `layered-cognitive-agent` 对 Hermes 类 Agent 能力的逐项检查与实现。每一项能力必须具备代码或测试层面的实质变化，并以独立提交完成；空提交、纯格式变化和重复提交不计入完成数。

## 提交原则

每个提交只解决一个能力或一个不可再拆分的基础契约。提交完成后必须执行与改动相关的测试、检查工作区，并推送到远程 `main`。若某能力依赖前置能力，先完成前置提交并在本表中记录依赖。

## 能力路线

| 编号 | 能力 | 主要落点 | 验证重点 | 状态 |
|---:|---|---|---|---|
| 01 | 能力矩阵与路线基线 | 本文档 | 文档链接与工作区洁净 | 已提交 |
| 02 | 任务命令的统一标识 | `contracts` / command | 类型与幂等键 | 待实现 |
| 03 | Session Header | session spine | parent/fork/delegation 元数据 | 待实现 |
| 04 | durable task 创建事实 | Journal / command | 创建事实可追加 | 待实现 |
| 05 | task 状态投影 | projection registry | whole-value projection | 待实现 |
| 06 | step 状态模型 | task models | 节点状态与版本 | 待实现 |
| 07 | checkpoint 事实模型 | runtime / observability | 游标、状态引用、计划引用 | 待实现 |
| 08 | command 消费幂等 | command gateway | 重放不重复执行 | 待实现 |
| 09 | Agent Registry 持久化入口 | harness/agent | create/resume | 待实现 |
| 10 | Gateway 去除 concrete loop 分支 | gateway/runs | 仅依赖 loop registry | 待实现 |
| 11 | Profile 驱动 runtime 装配 | harness/profile | Loader/reconcile | 待实现 |
| 12 | Scoped plugin host | plugin kernel | run scope 隔离 | 待实现 |
| 13 | 动态计划输入契约 | declarative plans | JSON Schema/验证 | 待实现 |
| 14 | 计划预算策略 | control contributions | steps/time/cost | 待实现 |
| 15 | 计划版本与变更集 | plan models | 只修改未执行节点 | 待实现 |
| 16 | 重规划请求模型 | cognition contracts | retry/replace/ask/stop | 待实现 |
| 17 | 重规划安全闸 | phase graph | 计划变更审批 | 待实现 |
| 18 | 工具 manifest 风险字段 | tool protocol | side effect/risk | 待实现 |
| 19 | 工具版本选择 | registry | deterministic resolution | 待实现 |
| 20 | 工具参数严格校验 | tool gateway | additionalProperties=false | 待实现 |
| 21 | 工具 timeout/retry 策略 | tool runner | 分类错误处理 | 待实现 |
| 22 | 工具幂等键传递 | body/safe executor | envelope 到 adapter | 待实现 |
| 23 | 工具回执模型 | effect receipt | success/failure/unknown | 待实现 |
| 24 | 副作用前授权 | act controls | grant/scope/resource | 待实现 |
| 25 | 审批请求持久化 | approval | durable pause | 待实现 |
| 26 | 审批过期重校验 | approval resume | policy/data version | 待实现 |
| 27 | 敏感字段脱敏 | observability | journal/log redaction | 待实现 |
| 28 | 外部内容提示注入隔离 | context builder | data/instruction separation | 待实现 |
| 29 | 沙箱资源限制 | sandbox | network/fs/time/cpu | 待实现 |
| 30 | 只读工具策略 | tool policy | read-only profile | 待实现 |
| 31 | Memory 事实来源 | memory contracts | provenance/confidence | 待实现 |
| 32 | 记忆过期与删除 | memory provider | TTL/tombstone | 待实现 |
| 33 | RAG 检索证据链 | search/memory | source references | 待实现 |
| 34 | 上下文预算管理 | context budgeter | deterministic trimming | 待实现 |
| 35 | artifact manifest | file store | hash/content type/owner | 待实现 |
| 36 | 结果验证器契约 | verifier | business read-back | 待实现 |
| 37 | 部分成功结果 | outcome projection | explicit partial state | 待实现 |
| 38 | 补偿动作契约 | effect handlers | compensation eligibility | 待实现 |
| 39 | 超时恢复策略 | recovery graph | retry/resume/fail | 待实现 |
| 40 | 取消与停止语义 | command/runtime | cooperative cancellation | 待实现 |
| 41 | 事件回放 | journal/replay | deterministic replay | 待实现 |
| 42 | 多 Agent capability 衰减 | delegation | child grant subset | 待实现 |
| 43 | Agent handoff 事实 | team contracts | ownership transfer | 待实现 |
| 44 | Team shared memory 隔离 | team seam | tenant/session scope | 待实现 |
| 45 | 子 Agent 生命周期 | team runtime | disposal and cleanup | 待实现 |
| 46 | SSE whole-value projection | gateway/projection | seq/high-water mark | 待实现 |
| 47 | 任务轨迹结构化 | observability | model/tool/policy versions | 待实现 |
| 48 | 成本与预算观测 | cost projector | token/tool cost | 待实现 |
| 49 | 评测样例格式 | eval | replayable cases | 待实现 |
| 50 | 轨迹回放评测 | eval runner | regression comparison | 待实现 |
| 51 | 工具失败场景测试 | tests | timeout/business/unknown | 待实现 |
| 52 | 审批与恢复集成测试 | tests | pause/resume/recheck | 待实现 |
| 53 | 生产 profile smoke test | scripts/tests | real composition path | 待实现 |
| 54 | 文档与迁移验收门禁 | scripts/CI | architecture conformance | 待实现 |
| 55 | Hermes 示例场景 | docs/examples | end-to-end trace | 待实现 |

## 当前判定标准

“支持”必须同时满足三项：存在明确的类型或协议边界；存在一个可被运行时调用的实现路径；存在至少一个针对成功和失败分支的测试。只有文档描述而没有代码和测试的能力，标记为“设计存在”，不得标记为“已实现”。

“完成一次提交”要求提交信息使用 Conventional Commits，并明确说明能力、实现原因和验证命令。远程推送成功后，记录提交哈希和验证结果。
