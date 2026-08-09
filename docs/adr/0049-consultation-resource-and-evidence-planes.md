# ADR-0049: 咨询资源平面 + 证据平面 —— 闭合 board 协作

## 状态

Accepted

## 背景

board/consult 路径在 ADR-0035 统一了 `TeamAwareness` + `ConsultDuty`（进度门闩），
但生产 trace（「信贷办理业务流程…」）暴露三平面塌缩：

1. **资源分裂**：`budget.DEFAULT_DELEGATION_TIMEOUT_S=300`，Body 私藏
   `_DEFAULT_DELEGATE_TIMEOUT_S=30`；gate 短路构造的 `DelegationSpec` 无 timeout。
2. **盲重试**：transient 失败只 `attempts++` 后原样 fan-out；30s×3 角色×3 轮空转。
3. **证据断流**：timeout cancel 丢弃 stream 正文；duty 路径不写 outcomes；
   Lead 只能见「角色不可用」后 solo 兜底；`SynthesisCompleted(method=all_consulted)` 撒谎。
4. **解析失败污染用户正文**：`extract_json_block` 被 response_text 内嵌 ``` 截断，
   兜底把 raw JSON 整包当 `response_text`（违反 ADR-0045）。

根因不是「超时写小了」，而是 **Control / Resource / Evidence 未正交建模**。

## 决定

### 1. Resource 平面：委派超时单一事实源

- 唯一默认：`DEFAULT_DELEGATION_TIMEOUT_S`（contracts/budget）。
- 解析函数：`resolve_delegation_timeout_s`（显式 timeout_s > deadline 剩余 >
  min(默认, run 墙钟剩余) > 默认）。
- `DelegationSpec.timeout_s` 可选字段；gate 短路/强制必须写入。
- **删除** Body 私有 30s 默认。

### 2. Evidence 平面：`ConsultationOutcome` 账本

- `ConsultDuty.outcomes: list[ConsultationOutcome]` 与 `member_status` 正交：
  - status → 还要不要问
  - outcomes → 综合时用什么
- disposition：`completed | partial | timeout | validation_failed | error`
- usable：完整成功或 partial 达到 `min_usable_partial_chars`
- `RoleStatus.DONE_PARTIAL`：有可用部分证据的终态（不重试）

### 3. Transport：Deadline = Harvest

- `InternalTransport.wait_result` 超时 **不 raise**：cancel 后 grace 收割
  handler 返回的 Observation（含 partial）。
- `CognitiveAgent` 对 `CancelledError`：drain stream partial buffer，返回
  `Result(status=CANCELED, output=partial)`。
- stream 路径 `append_run_partial`（contextvar），不依赖 journal 反向控制。

### 4. ConsultPolicy：证据驱动下一步

- `compute_required_action_from_duty`：usable partial 不重试；empty timeout
  在 max_attempts 内可重试；耗尽 → FAILED。
- `MustConsultAllMembers` 只 fan-out policy 选出的角色，并挂载 timeout_s。
- `SynthesisCompleted.method` ∈ `{full, partial, solo_fallback}`（按证据完备度）。

### 5. Decision 防腐闭环

- 字符串感知花括号匹配优先于 ``` 围栏提取。
- 解析失败：`_salvage_response_text`，禁止 raw JSON 整包成为用户正文。

## 后果

- 正面：board 协作可在合理预算内完成；partial 可综合；叙事诚实；无第二套超时默认。
- 负面：`ConsultDuty` 字段扩展；`RoleStatus` 增 `DONE_PARTIAL`；synthesis method
  字符串变更（旧 `all_consulted` 废弃）。
- 中性：routing 路径 `results` 语义保留；journal 仍为投影。

## 相关

- Builds on：ADR-0035、ADR-0036、ADR-0037、ADR-0045
- Does not supersede：五层分层、封闭 TeamStrategy
