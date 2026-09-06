# Agent Note: Runtime DSH 收敛缝 — ModelContext vs ControlState

Status: implemented

## Problem

LCA 观测面（Session / fold / derive_messages）与运行时认知面（AgentState.history / build_tool_history）对 model-visible 上下文各有一套构建路径，导致 replay 与 live 可能不一致。Resume 与 crash recovery 同样存在 Session fold 与 Transport 内存路径并行。Reducer 被误用于承担 model wire 构建，违背「事实 SSOT + 投影派生」分层。

## Decision

按 ADR-0191 实施四态分离：Facts（Session.append）、Model-visible（ModelContextAssembler）、Control（RunCommitter / Reducer 演进）、Ephemeral（loop phase）。运行时 LLM 只读 assembler；checkpoint 三边界 fail-closed；cold load 走 repair_interrupted_turn；transport resume 以 recover_live_agent 为权威；StepTreeFoldDeriver 在 live run 仅读 Session 快照。

## Alternatives considered

- **删 Reducer 全 DSH 化**：否决；C4/C5/envelope/TerminalOutcome 需要显式 commit seam。
- **双路径 + 加强测试**：否决；drift 不可消除，只延迟暴露。
- **快照 resume**：否决；不可审计，与 ADR-0186 冲突。

## Verification

- `I-MV-RUNTIME-1` parity 测试通过；cognition 生产路径无 `build_tool_history`。
- checkpoint integration 证明 flush 失败不 dispatch LLM/tool。
- cold restore 对 open turn 产出 DSH 对齐 synthetic closers。
- transport resume 经 `assert_resume_allowed` 校验 Session 事实后再接受。

## Consequences

- ASK_HUMAN 答案经 `append_human_answer_surface` 写入 durable surface。
- TurnControlUnit 投影注册于 `bundles/session-runtime.yaml`；gates 经 `turn_control_reader` 读 Session 投影。
- RunCommitter.commit_turn append `turn.control.v1` facts；`DefaultReducer` 为默认实现。
