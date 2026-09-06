# Session 事件生命周期映射（DSH ↔ LCA 生产消费）

> 配套 [session-event-pipeline-spec.md](session-event-pipeline-spec.md) 与 [ADR-0191](../adr/0191-runtime-loop-dsh-convergence-and-control-plane.md)。
> 生产入口：`Session.append`；catalog 发射 seam：`lca/infrastructure/session/lifecycle_emit.py`。

## 1. 回合时序（规范顺序）

```text
begin_turn ──► accept_user_message ──► begin_step ──► request_model
      │                                      │               │
      │                                      │         [checkpoint llm/stream]
      │                                      │               │
      │                                      │         model stream (SSE, 不落盘)
      │                                      │               │
      │                                      │         complete_model / fail_model
      │                                      │         (surface assistant + header 由 ModelVisibleHook)
      │                                      │               │
      │                                      │         [tool body + checkpoint tools/execute]
      │                                      │               │
      │                                      │         turn.control.v1 (commit_turn)
      │                                      │               │
      │                                      └──► end_step ──┘
      └──► end_turn
```

## 2. 事件对照表

| 阶段 | DSH | LCA catalog | 生产 seam | 主要消费方 |
|---|---|---|---|---|
| 回合开始 | `turn/start` | `turn.started.v1` | `lifecycle_emit.begin_turn` | `session_stats`, `session_turn_outline`, `agent_state` |
| 用户消息 | `user/message` | `message.accepted.v1` + `spine.llm.request.header` surface | `accept_user_message` | `derive_messages`, `session_turn_outline`, title |
| 步开始 | `step/start` | `step.started.v1` | `begin_step` / `request_model` | `session_stats`, repair/query |
| 模型请求前 | checkpoint `llm/stream` | `model.requested.v1` | `request_model` | `session_stats`, token_usage |
| 模型请求 | header fold | `spine.llm.request.header` | `ModelVisibleHook.capture_pre_llm` | `derive_messages`, parity tests |
| 流式 chunk | `assistant/chunk` | `thinking.delta.v1` (optional) | journal adapter (Session 镜像待启用) | 不进 derive |
| 模型完成 | `assistant/message` | `model.completed.v1` + `assistant.responded.v1` + surface | `complete_model` + hook post | `derive_messages`, token_usage |
| 模型失败 | `llm/retry` 族 | `model.failed.v1` | `fail_model` | stats / doctor |
| 工具结果 | `tool/result` | `spine.body.tool.execute.end` | `emit_body_tool_execute_end` | `derive_messages`, journal_fold |
| 控制提交 | — | `turn.control.v1` | `commit_turn` | `TurnControlUnit`, gates |
| 步结束 | `step/end` | `step.ended.v1` | `end_step` | `session_stats`, `agent_state` |
| 回合结束 | `turn/end` | `turn.ended.v1` | `end_turn` | recovery, projection_cache |
| HIL 恢复 | — | `approval.persisted/resolved.v1` | approval + transport | `recover_live_agent` |
| 检查点 | — | `session.checkpoint.v1` | checkpoint policy | `recover_live_agent` |
| Crash repair | synthetic closers | `step.ended.v1`, `turn.ended.v1`, surface tool/result | `repair_interrupted_turn` | cold restore |

## 3. 平面分工

| 平面 | 拥有 | 不重复 |
|---|---|---|
| Session catalog (`.v1`) | 回合/步边界、模型审计、审批、surface compat | 工具 invocation 细节 |
| Spine EP (130) | 认知/执行 instrumentation、header、cursor EP | 替代 catalog 边界事件 |
| Ephemeral (SSE) | UI 流式帧 | 可恢复事实 |

## 4. 验证

```sh
uv run pytest tests/infrastructure/test_lifecycle_emit.py \
  tests/scenarios/test_recording_loop.py \
  tests/scenarios/test_adr0191_runtime_convergence.py -q
```
