# Hermes 能力实现进度台账

本台账只记录本轮新增的、已经完成测试并推送至远程 `main` 的能力提交。仓库原有提交不计入本轮能力数量。

| 序号 | 能力 | 提交 | 验证 |
|---:|---|---|---|
| 01 | Hermes 能力矩阵与提交路线基线 | 已推送 | 文档审查 |
| 02 | 统一命令类型与命令 ID | 已推送 | command identity tests |
| 03 | SessionHeader 创建时不变量 | 已推送 | session header tests |
| 04 | durable TaskCreated 事实事件 | 已推送 | event registry tests |
| 05 | 可回放任务生命周期投影 | `eeea53f0` | 3 tests + ruff |
| 06 | TaskStep 生命周期状态契约 | `d376994c` | 4 tests + ruff |
| 07 | Checkpoint 计划引用一致性 | `117885fc` | 8 tests + ruff |
| 08 | 受约束 ReplanRequest | `e28e230d` | 4 tests + ruff |
| 09 | BudgetLimits 正值边界 | `3d1cad7e` | 4 tests + ruff |
| 10 | 重规划禁止修改已完成步骤 | `673f108c` | 6 tests + ruff |
| 11 | 工具治理元数据 | `3b76105b` | 5 tests + ruff |
| 12 | 工具风险审批判定 | `a57ddc03` | 6 tests + ruff |
| 13 | 工具注册名边界校验 | `76531231` | 4 tests + ruff |
| 14 | EffectReceipt 统一回执 | `20deca1f` | 5 tests + ruff |
| 15 | ArtifactManifest 产物清单 | `5ab0c263` | 2 tests + ruff |
| 16 | TaskResultVerifier 验证契约 | `611d5eff` | 4 tests + ruff |
| 17 | 部分成功任务状态 | `e8570ab8` | 70 tests + ruff |
| 18 | ApprovalRequestSnapshot 过期快照 | `f773bdba` | 377 tests + ruff |
| 19 | SessionEvent 流顺序验证 | `249f6f9b` | 5 tests + ruff |
| 20 | Gateway 回执归一化 | `34c62582` | 6 tests + ruff |
| 21 | TaskProjection 乱序事件保护 | `e0f45249` | 2 tests + ruff |
| 22 | SessionStore 恢复边界验证 | `85d62abc` | 378 tests + ruff |
| 23 | Step 事件坐标不变量 | `3aa5bc9e` | 376 tests + ruff |
| 24 | EffectReceipt Gateway 兼容解析 | `34c62582` | 6 tests + ruff |

## 进度规则

每一项能力必须具有明确的类型、协议或实现边界，并至少覆盖成功和失败或拒绝分支。每次提交完成后均执行针对性测试、代码风格检查和 `git diff --check`，随后推送到 `origin/main`。后续提交从第 25 项继续，不以仓库原有的 722 个历史提交冒充本轮能力完成数。
